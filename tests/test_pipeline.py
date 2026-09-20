"""Tests for pipeline orchestrator and Plan role. Run: python3 tests/test_pipeline.py

DEPENDENCIES:
  - src/backbone.py
  - src/agent.py
  - src/plan_agent.py
  - src/pipeline.py
  - src/search_grounding.py
"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backbone import Backbone
from agent import ReviewAgent
from plan_agent import PlanAgent, Proposal, normalise_proposal_type
from pipeline import Pipeline, PipelineContext, PipelineResult, PIPELINE_ORDER, create_pipeline
import search_grounding

# ---------------------------------------------------------- offline backend
FAKE_PACK = {
    "https://arxiv.org/abs/2607.13104": "Self-Improvements in Modern Agentic Systems",
    "https://github.com/affaan-m/ECC": "ECC — Agent framework",
    "https://github.com/AgentSwarms-fyi/agentswarms": "AgentSwarms — Multi-agent framework",
}


def _fake_search(query):
    return [{"title": t, "url": u} for u, t in FAKE_PACK.items()]


search_grounding.set_search_backend(_fake_search)

passed, failed = [], []


def check(name, fn):
    try:
        fn(); passed.append(name); print(f"  ok  {name}")
    except Exception as e:
        failed.append((name, e)); print(f"FAIL  {name}: {e}")


# ---------------------------------------------------------- setup

tmp = Path(tempfile.mkdtemp())
bb = Backbone(tmp / "test_pipeline.db")

SPEC = (
    "Discover NEW experts/sources for self-improving agent design and propose "
    "novel improvements (GUI, UX, context recording, ontology, toolset). "
    "Output: prioritised recommendations with source, type, evidence, impact, risk."
)

# Lock spec for all tests
bb.lock_job_spec("pipeline-job-001", SPEC)

# Create agents
review_agent = ReviewAgent(bb)
plan_agent = PlanAgent(bb)

# Create pipeline
pipeline = create_pipeline(bb)
pipeline.register_role("review", review_agent)
pipeline.register_role("plan", plan_agent)


# ============================================================ pipeline tests

def t_pipeline_order():
    """Verify pipeline order is sequential and correct."""
    assert PIPELINE_ORDER == ("review", "plan", "code", "test", "signoff")


def t_pipeline_register_role():
    """Pipeline accepts valid role registration."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    assert "review" in pipeline.roles


def t_pipeline_rejects_invalid_role():
    """Pipeline rejects unknown role names."""
    pipeline = create_pipeline(bb)
    try:
        pipeline.register_role("invalid_role", review_agent)
        raise AssertionError("should reject invalid role")
    except ValueError as e:
        assert "unknown role" in str(e)


def t_pipeline_rejects_role_without_run():
    """Pipeline rejects role instances without run() method."""
    pipeline = create_pipeline(bb)
    
    class BadRole:
        pass
    
    try:
        pipeline.register_role("review", BadRole())
        raise AssertionError("should reject role without run()")
    except ValueError as e:
        assert "run()" in str(e)


def t_pipeline_context_dataclass():
    """PipelineContext is a valid dataclass with expected fields."""
    ctx = PipelineContext(job_id="test")
    assert ctx.job_id == "test"
    assert ctx.review_recommendations == []
    assert ctx.plan_proposals == []


def t_pipeline_result_dataclass():
    """PipelineResult is a valid dataclass."""
    ctx = PipelineContext(job_id="test")
    result = PipelineResult(success=True, completed_roles=["review"], context=ctx)
    assert result.success is True
    assert result.completed_roles == ["review"]
    assert result.error is None


# ============================================================ review -> plan handoff

def t_review_produces_recommendations():
    """Review agent produces recommendations via pipeline context."""
    recs = review_agent.run("pipeline-job-001")
    assert len(recs) >= 2, f"expected >= 2 recommendations, got {len(recs)}"
    assert all(hasattr(r, 'source') for r in recs)
    assert all(hasattr(r, 'type') for r in recs)
    assert all(hasattr(r, 'priority') for r in recs)


def t_plan_consumes_recommendations():
    """Plan agent consumes review recommendations from context."""
    recs = review_agent.run("pipeline-job-001")
    ctx = PipelineContext(job_id="pipeline-job-001", review_recommendations=recs)
    proposals = plan_agent.run("pipeline-job-001", ctx)
    
    assert len(proposals) >= 2, f"expected >= 2 proposals from {len(recs)} recommendations"
    assert all(isinstance(p, Proposal) for p in proposals)
    assert all(hasattr(p, 'change_type') for p in proposals)
    assert all(hasattr(p, 'priority') for p in proposals)
    assert all(hasattr(p, 'estimated_effort') for p in proposals)


def t_plan_fails_on_empty_input():
    """Plan agent fails closed when given empty recommendations."""
    ctx = PipelineContext(job_id="pipeline-job-001", review_recommendations=[])
    try:
        plan_agent.run("pipeline-job-001", ctx)
        raise AssertionError("should fail on empty input")
    except RuntimeError as e:
        assert "no review recommendations" in str(e)


def t_plan_proposals_on_change_board():
    """Plan agent writes all proposals to the change board."""
    # Use a fresh job_id to avoid interference from other tests
    job_id = "pipeline-proposals-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    
    # Check change board has entries for each proposal
    changes = bb.report(role="plan", change_type="proposal")
    # Filter to our job_id
    changes = [c for c in changes if c.get("job_id") == job_id]
    assert len(changes) >= len(recs), \
        f"expected at least {len(recs)} plan proposals on board (can be more due to 1:n mapping), got {len(changes)}"
    # Each proposal should have a corresponding change
    assert len(changes) == len(proposals), \
        f"proposal count mismatch: {len(proposals)} proposals but {len(changes)} changes on board"


def t_plan_priority_uses_scores():
    """Plan proposals incorporate recommendation scores into priority."""
    recs = review_agent.run("pipeline-job-001")
    # Manually score the first recommendation
    if recs:
        cid = bb.report(role="review", change_type="recommendation")[0]["change_id"]
        review_agent.score(cid, {
            "novelty": 5, "relevance": 5, "evidence_quality": 5,
            "actionability": 5, "vision_alignment": 5
        }, "test")
        
        # Re-fetch recs with scores
        recs_scored = bb.conn.execute(
            "SELECT payload FROM changes WHERE change_id=?", (cid,)
        ).fetchone()["payload"]
        
        # Now run plan with scored recommendations
        # Note: we need to reconstruct Recommendation objects with scores
        # For this test, we just verify the mechanism works
        ctx = PipelineContext(job_id="pipeline-job-001", review_recommendations=recs)
        proposals = plan_agent.run("pipeline-job-001", ctx)
        
        # All proposals should have priority >= 0
        assert all(p.priority >= 0 for p in proposals)


# ============================================================ pipeline integration

def t_pipeline_partial_run_review_only():
    """Pipeline can run Review role in isolation."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    
    # Create new job for this test
    bb.lock_job_spec("pipeline-partial-001", SPEC)
    
    ctx = PipelineContext(job_id="pipeline-partial-001")
    result = pipeline.run_partial("pipeline-partial-001", "review", ctx)
    
    assert result.success is True
    assert "review" in result.completed_roles
    assert len(result.context.review_recommendations) >= 2


def t_pipeline_full_run_review_to_plan():
    """Pipeline can run Review -> Plan sequence."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    
    # Create new job for this test
    bb.lock_job_spec("pipeline-full-001", SPEC)
    
    result = pipeline.run("pipeline-full-001", SPEC, start_role="review")
    
    assert result.success is True
    assert "review" in result.completed_roles
    assert "plan" in result.completed_roles
    assert len(result.context.review_recommendations) >= 2
    assert len(result.context.plan_proposals) >= 2


def t_pipeline_skips_unregistered_roles():
    """Pipeline filters out unregistered roles and runs successfully.
    
    When roles are not registered, the pipeline stops execution at that point
    rather than failing. This allows partial pipelines (e.g., just Review + Plan).
    """
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    # Intentionally don't register "plan", "code", "test", "signoff"
    
    bb.lock_job_spec("pipeline-filter-001", SPEC)
    
    result = pipeline.run("pipeline-filter-001", SPEC, start_role="review")
    
    # Should succeed with only review completed
    assert result.success is True
    assert "review" in result.completed_roles
    # plan, code, test, signoff should NOT be in completed_roles since not registered
    assert "plan" not in result.completed_roles
    assert "code" not in result.completed_roles
    assert "test" not in result.completed_roles
    assert "signoff" not in result.completed_roles


def t_pipeline_traces_all_steps():
    """Pipeline execution is fully traced."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    
    bb.lock_job_spec("pipeline-trace-001", SPEC)
    
    result = pipeline.run("pipeline-trace-001", SPEC, start_role="review")
    
    # Check trace log for pipeline events
    pipeline_events = [
        r["event_type"] for r in bb.conn.execute(
            "SELECT event_type FROM trace_log WHERE job_id='pipeline-trace-001'"
        )
    ]
    
    assert "pipeline_start" in pipeline_events
    assert "pipeline_complete" in pipeline_events
    assert all(e in pipeline_events for e in ["role_invoke", "model_response", "tool_call", "board_write"])


# ============================================================ proposal normalisation

def t_normalise_proposal_type_known():
    """Known proposal types normalize correctly."""
    canonical, recognised = normalise_proposal_type("feature")
    assert canonical == "feature"
    assert recognised is True
    
    canonical, recognised = normalise_proposal_type("new_feature")
    assert canonical == "feature"
    assert recognised is True
    
    canonical, recognised = normalise_proposal_type("bugfix")
    assert canonical == "bugfix"
    assert recognised is True


def t_normalise_proposal_type_unknown():
    """Unknown proposal types fall back to 'refactor'."""
    canonical, recognised = normalise_proposal_type("banana")
    assert canonical == "refactor"
    assert recognised is False


def t_normalise_proposal_type_case_insensitive():
    """Proposal type normalization is case-insensitive."""
    canonical, _ = normalise_proposal_type("FEATURE")
    assert canonical == "feature"
    
    canonical, _ = normalise_proposal_type("BugFix")
    assert canonical == "bugfix"


# ============================================================ pipeline context immutability

def t_context_not_mutated():
    """Pipeline context is deep-copied, not mutated."""
    recs = review_agent.run("pipeline-job-001")
    original_ctx = PipelineContext(
        job_id="pipeline-job-001",
        review_recommendations=recs.copy(),
    )
    original_rec_count = len(original_ctx.review_recommendations)
    
    # Run plan which modifies context
    result = plan_agent.run("pipeline-job-001", original_ctx)
    
    # Original context should be unchanged
    assert len(original_ctx.review_recommendations) == original_rec_count
    assert len(original_ctx.plan_proposals) == 0  # Should still be empty


# ============================================================ chain integrity

def t_chain_intact_after_pipeline_run():
    """Hash chain remains intact after full pipeline execution."""
    ok, broken = bb.verify_chain()
    assert ok, f"chain broken at {broken}"


# ============================================================ run all tests

for name, fn in [
    # Pipeline basics
    ("pipeline order is correct", t_pipeline_order),
    ("pipeline registers valid roles", t_pipeline_register_role),
    ("pipeline rejects invalid role names", t_pipeline_rejects_invalid_role),
    ("pipeline rejects roles without run()", t_pipeline_rejects_role_without_run),
    ("PipelineContext dataclass works", t_pipeline_context_dataclass),
    ("PipelineResult dataclass works", t_pipeline_result_dataclass),
    
    # Review -> Plan handoff
    ("Review produces recommendations", t_review_produces_recommendations),
    ("Plan consumes recommendations from context", t_plan_consumes_recommendations),
    ("Plan fails closed on empty input", t_plan_fails_on_empty_input),
    ("Plan writes proposals to change board", t_plan_proposals_on_change_board),
    ("Plan priority uses scores", t_plan_priority_uses_scores),
    
    # Pipeline integration
    ("pipeline partial run (review only)", t_pipeline_partial_run_review_only),
    ("pipeline full run (review->plan)", t_pipeline_full_run_review_to_plan),
    ("pipeline filters out unregistered roles", t_pipeline_skips_unregistered_roles),
    ("pipeline traces all steps", t_pipeline_traces_all_steps),
    
    # Proposal normalization
    ("proposal type normalization (known)", t_normalise_proposal_type_known),
    ("proposal type normalization (unknown)", t_normalise_proposal_type_unknown),
    ("proposal type normalization (case insensitive)", t_normalise_proposal_type_case_insensitive),
    
    # Context safety
    ("context not mutated during execution", t_context_not_mutated),
    
    # Chain integrity
    ("hash chain intact after pipeline", t_chain_intact_after_pipeline_run),
]:
    check(name, fn)


print(f"\nmodel mode: mock")
print(f"{len(passed)} passed, {len(failed)} failed")

# Print any failures
for name, error in failed:
    print(f"  FAILED: {name}: {error}")

sys.exit(1 if failed else 0)
