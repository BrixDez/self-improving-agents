"""
signoff_agent.py — Sign off role for self-improving agent system.
============================================================

DESIGN:
  - Final role in the pipeline: Review -> Plan -> Code -> Test -> Sign off
  - Reviews test results from Test role
  - Makes final decision: accept, reject, or hold for review
  - All decisions written to change board
  - Fail-closed: missing critical information aborts the pipeline
  - Human sign-off required for Tier 2 changes (AGENTS.md rule #4)

CONTRACT:
  Input: PipelineContext with test_results
  Output: SignOffDecision object with final verdict
  
  The Sign off role does NOT apply changes - it only records the decision.
  Actual application of changes is a separate concern (future work).

KEDB considerations:
  - Model may fabricate approvals -> constrain at parser boundary
  - Empty input -> fail-closed (no results to sign off on)
  - Sign off never grades its own work (AGENTS.md rule #5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backbone import Backbone
    from pipeline import PipelineContext


# ---------------------------------------------------------------- constants

# Valid sign-off decisions
SIGN_OFF_DECISIONS = ("accept", "reject", "hold_for_review")

# Thresholds for automatic decision making (configurable)
AUTO_ACCEPT_THRESHOLD = 0.95  # 95% of tests passing with no critical failures
AUTO_HOLD_THRESHOLD = 0.70   # 70% or below: hold for review
CRITICAL_FAILURES_MAX = 0    # Any critical failure (priority >= 4) means reject


@dataclass
class SignOffDecision:
    """Final decision from the Sign off role."""
    # The decision
    decision: str  # "accept", "reject", "hold_for_review"
    
    # Decision rationale
    rationale: str
    
    # Summary of what was reviewed
    test_results_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    held_count: int = 0
    critical_failures_count: int = 0
    
    # References
    job_id: str = ""
    change_ids: list[int] = field(default_factory=list)  # All change IDs being signed off
    
    # Metadata
    priority: float = 0.0
    decision_id: int | None = None  # change board ID for this decision
    
    def to_change_payload(self) -> dict:
        """Convert to payload format for change board."""
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "test_results_count": self.test_results_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "held_count": self.held_count,
            "critical_failures_count": self.critical_failures_count,
            "job_id": self.job_id,
            "change_ids": self.change_ids,
            "priority": self.priority,
        }


# ---------------------------------------------------------------- decision logic

def calculate_decision(test_results: list, auto_mode: bool = True) -> tuple[str, str]:
    """Calculate sign-off decision based on test results.
    
    Args:
        test_results: List of test result objects (must have verdict and priority)
        auto_mode: If True, make automatic decision based on thresholds
        
    Returns:
        Tuple of (decision, rationale)
    """
    if not test_results:
        return "hold_for_review", "No test results to evaluate"
    
    # Count results
    passed = sum(1 for r in test_results if r.verdict == "pass")
    failed = sum(1 for r in test_results if r.verdict == "fail")
    held = sum(1 for r in test_results if r.verdict == "hold")
    total = len(test_results)
    
    # Count critical failures (priority >= 4)
    critical_failures = sum(
        1 for r in test_results 
        if r.verdict == "fail" and getattr(r, "priority", 0) >= 4
    )
    
    pass_rate = passed / total if total > 0 else 0
    
    # Decision logic
    if critical_failures > CRITICAL_FAILURES_MAX:
        return "reject", \
            f"{critical_failures} critical test failure(s) detected. " \
            f"Pass rate: {pass_rate:.1%}"
    
    elif pass_rate >= AUTO_ACCEPT_THRESHOLD and auto_mode:
        return "accept", \
            f"All tests passing at {pass_rate:.1%} with no critical failures"
    
    elif pass_rate <= AUTO_HOLD_THRESHOLD:
        return "hold_for_review", \
            f"Low pass rate: {pass_rate:.1%} ({passed}/{total})"
    
    else:
        return "hold_for_review", \
            f"Mixed results: {passed} passed, {failed} failed, {held} held"


# ---------------------------------------------------------------- the agent

class SignOffAgent:
    """Sign off role: makes final decision based on test results.
    
    All actions flow through the Backbone's audited API.
    Fail-closed: missing critical information aborts the pipeline.
    Human sign-off required for Tier 2 changes (AGENTS.md rule #4).
    Sign off never grades its own work (AGENTS.md rule #5).
    """

    def __init__(self, bb: "Backbone", role: str = "signoff", auto_mode: bool = True):
        self.bb = bb
        self.role = role
        self.model = None  # Sign off uses deterministic logic, no LLM
        self.auto_mode = auto_mode  # If False, always holds for human review

    def run(self, job_id: str, context: "PipelineContext") -> SignOffDecision:
        """Make final sign-off decision based on test results.
        
        Args:
            job_id: The job identifier
            context: PipelineContext containing test_results
            
        Returns:
            SignOffDecision object with final verdict
            
        Raises:
            RuntimeError: If no test results to evaluate
        """
        import hashlib
        
        # 1. Goal-drift guard: spec re-injected verbatim at handoff
        spec = self.bb.get_spec_verbatim(job_id)
        
        # 2. Extract test results from context
        test_results = context.test_results if context else []
        
        # 3. Fail-closed: no test results = cannot sign off
        if not test_results:
            self.bb.trace("tool_call", self.role, {
                "tool": "signoff_validation",
                "status": "empty_input_abort",
                "detail": "no test results to sign off on — aborting",
            }, job_id=job_id)
            raise RuntimeError("Sign off role: no test results to sign off on")
        
        # 4. Trace the sign off invocation
        self.bb.trace("role_invoke", self.role, {
            "input_type": "test_results",
            "input_count": len(test_results),
            "spec_sha256_tail": hashlib.sha256(spec.encode()).hexdigest()[-12:],
            "auto_mode": self.auto_mode,
        }, job_id=job_id)
        
        # 5. Collect all change IDs from previous roles for reference
        change_ids = []
        for row in self.bb.conn.execute(
            "SELECT change_id FROM changes WHERE job_id=?", (job_id,)
        ):
            change_ids.append(row["change_id"])
        
        # 6. Count results
        passed = sum(1 for r in test_results if r.verdict == "pass")
        failed = sum(1 for r in test_results if r.verdict == "fail")
        held = sum(1 for r in test_results if r.verdict == "hold")
        total = len(test_results)
        
        # Count critical failures
        critical_failures = sum(
            1 for r in test_results 
            if r.verdict == "fail" and getattr(r, "priority", 0) >= 4
        )
        
        # Trace the summary
        self.bb.trace("tool_call", self.role, {
            "tool": "result_summary",
            "total": total,
            "passed": passed,
            "failed": failed,
            "held": held,
            "critical_failures": critical_failures,
        }, job_id=job_id)
        
        # 7. Calculate decision
        decision, rationale = calculate_decision(test_results, self.auto_mode)
        
        # If not in auto_mode, always hold for human review
        if not self.auto_mode:
            decision = "hold_for_review"
            rationale = f"Auto-mode disabled: {passed} passed, {failed} failed, {held} held. Requires human review."
        
        # 8. Create decision object
        decision_obj = SignOffDecision(
            decision=decision,
            rationale=rationale,
            test_results_count=total,
            passed_count=passed,
            failed_count=failed,
            held_count=held,
            critical_failures_count=critical_failures,
            job_id=job_id,
            change_ids=change_ids,
            priority=0,  # Sign off decisions have neutral priority
        )
        
        # 9. Write decision to change board
        change_id = self.bb.propose_change(
            job_id, self.role, "signoff_decision",
            f"{decision.upper()}: {rationale[:80]}",
            decision_obj.to_change_payload(),
            tier=2 if decision == "accept" else 3,  # Accept requires human sign-off (Tier 2)
        )
        decision_obj.decision_id = change_id
        
        # 10. For accepted decisions, mark all previous changes as accepted
        #     (This is the sign-off action - applying the decision to the change set)
        if decision == "accept":
            # In auto-mode, we can mark changes as accepted
            # In production, this would require human intervention for Tier 2
            for cid in change_ids:
                # Only accept Tier 3 changes (Tier 2 requires human sign-off)
                row = self.bb.conn.execute(
                    "SELECT tier FROM changes WHERE change_id=?", (cid,)
                ).fetchone()
                if row and row["tier"] == 3:
                    self.bb.decide_change(cid, "accepted", self.role)
            
            self.bb.trace("board_write", self.role, {
                "action": "batch_accept",
                "change_ids": change_ids,
                "count": len(change_ids),
            }, job_id=job_id)
        
        elif decision == "reject":
            # Mark all changes as rejected
            for cid in change_ids:
                self.bb.decide_change(cid, "rejected", self.role)
            
            self.bb.trace("board_write", self.role, {
                "action": "batch_reject",
                "change_ids": change_ids,
                "count": len(change_ids),
            }, job_id=job_id)
        
        # 11. Trace completion
        self.bb.trace("model_response", self.role, {
            "decision": decision,
            "rationale": rationale[:200],
            "test_results_count": total,
            "passed": passed,
            "failed": failed,
        }, job_id=job_id)
        
        return decision_obj

    def manual_sign_off(self, job_id: str, decision: str, rationale: str, 
                       human: str = "human") -> SignOffDecision:
        """Manual sign-off by a human operator.
        
        This is used when auto_mode is False and a human needs to make the decision.
        
        Args:
            job_id: The job identifier
            decision: One of "accept", "reject", "hold_for_review"
            rationale: Human-provided rationale
            human: The human operator identifier
            
        Returns:
            SignOffDecision object
        """
        if decision not in SIGN_OFF_DECISIONS:
            raise ValueError(f"invalid decision: {decision}. Must be one of {SIGN_OFF_DECISIONS}")
        
        # Get all change IDs for this job
        change_ids = []
        for row in self.bb.conn.execute(
            "SELECT change_id FROM changes WHERE job_id=?", (job_id,)
        ):
            change_ids.append(row["change_id"])
        
        # Get test results count
        test_results = self.bb.conn.execute(
            "SELECT COUNT(*) FROM changes WHERE job_id=? AND role=? AND change_type=?",
            (job_id, "test", "test_result")
        ).fetchone()[0]
        
        passed = self.bb.conn.execute(
            "SELECT COUNT(*) FROM changes WHERE job_id=? AND role=? AND change_type=? AND payload LIKE '%\"verdict\":\"pass\"%'",
            (job_id, "test", "test_result")
        ).fetchone()[0]
        
        failed = self.bb.conn.execute(
            "SELECT COUNT(*) FROM changes WHERE job_id=? AND role=? AND change_type=? AND payload LIKE '%\"verdict\":\"fail\"%'",
            (job_id, "test", "test_result")
        ).fetchone()[0]
        
        held = test_results - passed - failed
        
        decision_obj = SignOffDecision(
            decision=decision,
            rationale=rationale,
            test_results_count=test_results,
            passed_count=passed,
            failed_count=failed,
            held_count=held,
            critical_failures_count=0,  # Not tracked in manual mode
            job_id=job_id,
            change_ids=change_ids,
            priority=0,
        )
        
        # Write decision to change board
        change_id = self.bb.propose_change(
            job_id, self.role, "signoff_decision",
            f"{decision.upper()}: {rationale[:80]}",
            decision_obj.to_change_payload(),
            tier=2,  # Manual sign-off is Tier 2
        )
        decision_obj.decision_id = change_id
        
        # Apply the decision to all changes
        if decision == "accept":
            for cid in change_ids:
                self.bb.decide_change(cid, "accepted", human)
        elif decision == "reject":
            for cid in change_ids:
                self.bb.decide_change(cid, "rejected", human)
        # hold_for_review: no action needed, changes remain open
        
        self.bb.trace("board_write", human, {
            "action": "manual_signoff",
            "decision": decision,
            "job_id": job_id,
            "change_ids": change_ids,
        }, job_id=job_id)
        
        return decision_obj


if __name__ == "__main__":
    # Quick smoke test
    from pathlib import Path
    from backbone import Backbone
    from pipeline import Pipeline, PipelineContext, create_pipeline
    from plan_agent import PlanAgent
    from code_agent import CodeAgent
    from test_agent import TestAgent, TestResult
    from agent import ReviewAgent
    import search_grounding
    
    # Set up offline search backend
    FAKE_PACK = {
        "https://arxiv.org/abs/2607.13104": "Self-Improvements in Modern Agentic Systems",
        "https://github.com/affaan-m/ECC": "ECC framework",
    }
    search_grounding.set_search_backend(lambda q: [
        {"title": t, "url": u} for u, t in FAKE_PACK.items()
    ])
    
    # Create backbone
    db = Path(__file__).resolve().parent.parent / "data" / "signoff_test.db"
    bb = Backbone(db)
    
    job_id = "job-signoff-001"
    spec = "Discover NEW experts/sources and propose novel improvements."
    
    # Lock spec and run Review -> Plan -> Code -> Test
    bb.lock_job_spec(job_id, spec)
    
    review_agent = ReviewAgent(bb)
    recs = review_agent.run(job_id)
    
    plan_agent = PlanAgent(bb)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    
    ctx.plan_proposals = proposals
    
    code_agent = CodeAgent(bb)
    code_changes = code_agent.run(job_id, ctx)
    
    ctx.code_changes = code_changes
    
    test_agent = TestAgent(bb)
    test_results = test_agent.run(job_id, ctx)
    
    ctx.test_results = test_results
    
    print(f"Test produced {len(test_results)} results")
    for r in test_results:
        print(f"  - {r.verdict}: {r.test_name}")
    
    # Create and run Sign off agent
    signoff_agent = SignOffAgent(bb, auto_mode=True)
    
    try:
        decision = signoff_agent.run(job_id, ctx)
        print(f"\nSign off decision: {decision.decision}")
        print(f"Rationale: {decision.rationale}")
        print(f"Results: {decision.passed_count} passed, {decision.failed_count} failed")
    except RuntimeError as e:
        print(f"\nSign off failed: {e}")
    
    # Verify chain
    ok, broken = bb.verify_chain()
    print(f"\nChain: {'OK' if ok else f'BROKEN at {broken}'}")
    
    bb.close()
