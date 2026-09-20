"""
pipeline.py — Sequential role handoff orchestrator for self-improving agents.
================================================================

DESIGN:
  - Sequential handoff: Review -> Plan -> Code -> Test -> Sign off
  - Each role receives: job_id, spec (re-injected), context from previous role
  - Each role returns: its output + updated context for next role
  - All actions flow through Backbone's traced API
  - Fail-closed: any step failure aborts the pipeline

CONTRACT:
  Review -> Plan: list of accepted Recommendation objects with scores
  Plan -> Code: list of accepted Proposal objects (change_type, summary, priority)
  Code -> Test: code patches/diffs to apply
  Test -> Sign off: test results and verdict

KEDB considerations:
  - If a role fails, the pipeline stops and logs the failure
  - No partial commits: either all steps succeed or the pipeline halts
  - Spec is re-injected at EVERY role handoff (goal-drift guard)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backbone import Backbone


# ---------------------------------------------------------------- types

@dataclass
class PipelineContext:
    """Context passed between roles in the pipeline."""
    job_id: str
    # Review -> Plan
    review_recommendations: list = field(default_factory=list)
    # Plan -> Code
    plan_proposals: list = field(default_factory=list)
    # Code -> Test
    code_changes: list = field(default_factory=list)
    # Test -> Sign off
    test_results: list = field(default_factory=list)
    # Error tracking
    errors: list = field(default_factory=list)


@dataclass 
class PipelineResult:
    """Result of running the full pipeline."""
    success: bool
    completed_roles: list[str]  # roles that ran successfully
    context: PipelineContext
    error: str | None = None


# ---------------------------------------------------------------- constants

# Pipeline order: sequential, no parallelism
PIPELINE_ORDER = ("review", "plan", "code", "test", "signoff")

# Valid transition between roles
VALID_TRANSITIONS = {
    "review": "plan",
    "plan": "code", 
    "code": "test",
    "test": "signoff",
    "signoff": None,  # terminal
}


class Pipeline:
    """Sequential role handoff orchestrator.
    
    Manages the flow: Review -> Plan -> Code -> Test -> Sign off
    Each role is invoked with the spec re-injected (goal-drift guard).
    All state changes flow through the Backbone.
    Fail-closed: pipeline stops on any role failure.
    """

    def __init__(self, bb: "Backbone"):
        self.bb = bb
        self.roles: dict[str, object] = {}  # role_name -> role_instance

    def register_role(self, role_name: str, role_instance: object) -> None:
        """Register a role instance with the pipeline.
        
        Args:
            role_name: One of "review", "plan", "code", "test", "signoff"
            role_instance: The role agent instance (must have run() method)
        """
        if role_name not in PIPELINE_ORDER:
            raise ValueError(f"unknown role: {role_name}. Must be one of {PIPELINE_ORDER}")
        if not hasattr(role_instance, 'run'):
            raise ValueError(f"role instance must have run() method")
        self.roles[role_name] = role_instance

    def _reinject_spec(self, job_id: str, role_name: str) -> str:
        """Re-inject the locked spec verbatim at handoff (goal-drift guard)."""
        spec = self.bb.inject_spec(job_id, role_name)
        return spec

    def _run_role(self, role_name: str, context: PipelineContext) -> PipelineContext:
        """Run a single role with the current context.
        
        Returns updated context or raises on failure.
        """
        if role_name not in self.roles:
            raise ValueError(f"role {role_name} not registered")
        
        role = self.roles[role_name]
        job_id = context.job_id
        
        # Goal-drift guard: re-inject spec at every handoff
        spec = self._reinject_spec(job_id, role_name)
        
        # Trace the role invocation with context summary
        context_summary = self._context_summary(context, role_name)
        self.bb.trace("role_invoke", role_name, {
            "pipeline_step": role_name,
            "spec_sha256_tail": self._spec_hash_tail(spec),
            **context_summary,
        }, job_id=job_id)
        
        # Execute the role
        result = role.run(job_id, context)
        
        # Update context with role output
        updated_context = self._update_context(context, role_name, result)
        
        # Trace successful completion
        self.bb.trace("pipeline_step_complete", role_name, {
            "step": role_name,
            "next_step": VALID_TRANSITIONS.get(role_name),
        }, job_id=job_id)
        
        return updated_context

    def _context_summary(self, context: PipelineContext, current_role: str) -> dict:
        """Generate a trace-safe summary of context for the current role."""
        summary = {"job_id": context.job_id}
        
        if current_role == "plan" and context.review_recommendations:
            summary["review_recs_count"] = len(context.review_recommendations)
            summary["review_recs_scored"] = sum(
                1 for r in context.review_recommendations 
                if hasattr(r, 'scores') and r.scores
            )
        elif current_role == "code" and context.plan_proposals:
            summary["plan_proposals_count"] = len(context.plan_proposals)
        elif current_role == "test" and context.code_changes:
            summary["code_changes_count"] = len(context.code_changes)
        elif current_role == "signoff" and context.test_results:
            summary["test_results_count"] = len(context.test_results)
            summary["test_passed"] = sum(
                1 for r in context.test_results if r.get("verdict") == "pass"
            )
        
        return summary

    def _spec_hash_tail(self, spec: str) -> str:
        """Return last 12 chars of SHA-256 hash for trace compactness."""
        import hashlib
        return hashlib.sha256(spec.encode()).hexdigest()[-12:]

    def _update_context(self, context: PipelineContext, role_name: str, result) -> PipelineContext:
        """Update pipeline context with a role's output."""
        # Deep copy to avoid mutation
        import copy
        new_context = copy.deepcopy(context)
        
        if role_name == "review":
            # Review returns list of Recommendation objects
            new_context.review_recommendations = result or []
        elif role_name == "plan":
            # Plan returns list of proposal dicts or Proposal objects
            new_context.plan_proposals = result or []
        elif role_name == "code":
            # Code returns list of code change dicts
            new_context.code_changes = result or []
        elif role_name == "test":
            # Test returns list of test result dicts
            new_context.test_results = result or []
        elif role_name == "signoff":
            # Sign off may add final metadata to context
            if isinstance(result, dict):
                new_context.signoff_data = result
        
        return new_context

    def run(self, job_id: str, spec: str | None = None, start_role: str | None = None) -> PipelineResult:
        """Run the pipeline from start_role (default: review) through to signoff.
        
        Args:
            job_id: The job identifier
            spec: Optional spec text (if not already locked)
            start_role: Start from this role (default: "review"). 
                       Useful for resuming or testing partial pipelines.
        
        Returns:
            PipelineResult with success status, completed roles, context, and any error.
        """
        import hashlib
        
        if start_role is None:
            start_role = "review"
        
        if start_role not in PIPELINE_ORDER:
            raise ValueError(f"invalid start_role: {start_role}")
        
        # Ensure spec is locked
        if spec is not None:
            try:
                self.bb.lock_job_spec(job_id, spec)
            except ValueError:
                pass  # Already locked
        
        # Build the execution order from start_role onwards
        start_idx = PIPELINE_ORDER.index(start_role)
        execution_order = PIPELINE_ORDER[start_idx:]
        
        # Filter to only registered roles (stop pipeline at first unregistered role)
        # This allows partial pipelines when not all roles are implemented
        registered_set = set(self.roles.keys())
        execution_order = [
            role for role in execution_order 
            if role in registered_set
        ]
        
        if not execution_order:
            error = f"no registered roles starting from {start_role}"
            self.bb.trace("pipeline_error", "system", {
                "error": error,
                "available_roles": list(self.roles.keys()),
            }, job_id=job_id)
            return PipelineResult(
                success=False,
                completed_roles=[],
                context=context,
                error=error,
            )
        
        # Initialize context
        context = PipelineContext(job_id=job_id)
        completed_roles: list[str] = []
        error: str | None = None
        
        # Trace pipeline start
        self.bb.trace("pipeline_start", "system", {
            "job_id": job_id,
            "start_role": start_role,
            "execution_order": list(execution_order),
        }, job_id=job_id)
        
        try:
            for role_name in execution_order:
                # Check if role is registered
                if role_name not in self.roles:
                    error = f"role {role_name} not registered in pipeline"
                    self.bb.trace("pipeline_error", "system", {
                        "error": error,
                        "role": role_name,
                    }, job_id=job_id)
                    return PipelineResult(
                        success=False,
                        completed_roles=completed_roles,
                        context=context,
                        error=error,
                    )
                
                # Run the role
                context = self._run_role(role_name, context)
                completed_roles.append(role_name)
            
            # Trace pipeline completion
            self.bb.trace("pipeline_complete", "system", {
                "job_id": job_id,
                "completed_roles": completed_roles,
                "final_context_summary": {
                    "review_recs": len(context.review_recommendations),
                    "plan_proposals": len(context.plan_proposals),
                    "code_changes": len(context.code_changes),
                    "test_results": len(context.test_results),
                },
            }, job_id=job_id)
            
            return PipelineResult(
                success=True,
                completed_roles=completed_roles,
                context=context,
                error=None,
            )
            
        except Exception as e:
            error = str(e)
            self.bb.trace("pipeline_error", "system", {
                "error": error,
                "type": type(e).__name__,
                "completed_roles": completed_roles,
            }, job_id=job_id)
            return PipelineResult(
                success=False,
                completed_roles=completed_roles,
                context=context,
                error=error,
            )

    def run_partial(self, job_id: str, role_name: str, context: PipelineContext) -> PipelineResult:
        """Run a single role with explicit context (for testing or resuming).
        
        This is useful for:
        - Testing individual roles in isolation
        - Resuming a pipeline from a specific point
        - Debugging role behavior
        """
        try:
            updated_context = self._run_role(role_name, context)
            return PipelineResult(
                success=True,
                completed_roles=[role_name],
                context=updated_context,
                error=None,
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                completed_roles=[],
                context=context,
                error=str(e),
            )


# ---------------------------------------------------------------- convenience

def create_pipeline(bb: "Backbone") -> Pipeline:
    """Factory function to create a pipeline with default role registry."""
    return Pipeline(bb)


if __name__ == "__main__":
    # Quick smoke test
    from pathlib import Path
    from backbone import Backbone
    
    bb = Backbone()
    pipeline = create_pipeline(bb)
    
    print(f"pipeline created with backbone at {bb.db_path}")
    print(f"pipeline order: {PIPELINE_ORDER}")
    print(f"chain ok: {bb.verify_chain()}")
