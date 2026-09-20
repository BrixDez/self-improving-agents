"""Tests for Code role and Sign off role. Run: python3 tests/test_code_and_signoff.py

DEPENDENCIES:
  - src/backbone.py
  - src/agent.py
  - src/plan_agent.py
  - src/pipeline.py
  - src/code_agent.py
  - src/test_agent.py
  - src/signoff_agent.py
  - src/search_grounding.py
"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backbone import Backbone
from agent import ReviewAgent
from plan_agent import PlanAgent, Proposal
from pipeline import Pipeline, PipelineContext, create_pipeline
from code_agent import CodeAgent, CodeChange, CODE_CHANGE_TYPES, generate_file_path, generate_content, map_proposal_to_changes
from test_agent import TestAgent, TestResult
from signoff_agent import SignOffAgent, SignOffDecision, SIGN_OFF_DECISIONS, calculate_decision, AUTO_ACCEPT_THRESHOLD, AUTO_HOLD_THRESHOLD
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
bb = Backbone(tmp / "test_code_signoff.db")

SPEC = (
    "Discover NEW experts/sources for self-improving agent design and propose "
    "novel improvements (GUI, UX, context recording, ontology, toolset). "
    "Output: prioritised recommendations with source, type, evidence, impact, risk."
)

# Lock spec for all tests
bb.lock_job_spec("code-signoff-job-001", SPEC)

# Create agents
review_agent = ReviewAgent(bb)
plan_agent = PlanAgent(bb)
code_agent = CodeAgent(bb)
test_agent = TestAgent(bb)
signoff_agent = SignOffAgent(bb, auto_mode=True)


# ============================================================ code_agent constants tests

def t_code_change_types_constant():
    """CODE_CHANGE_TYPES contains expected change types."""
    expected = ["new_file", "modify_file", "delete_file", "refactor", "config_change", "dependency"]
    assert all(ct in CODE_CHANGE_TYPES for ct in expected)


# ============================================================ CodeChange dataclass

def t_code_change_dataclass():
    """CodeChange is a valid dataclass with expected fields."""
    change = CodeChange(
        change_type="new_file",
        file_path="src/test.py",
        content="print('hello')",
        proposal_id="prop-0",
        proposal_summary="Test proposal",
        proposal_type="feature",
        priority=3.0,
        estimated_lines=10,
    )
    assert change.change_type == "new_file"
    assert change.file_path == "src/test.py"
    assert change.content == "print('hello')"
    assert change.proposal_id == "prop-0"
    assert change.priority == 3.0


def t_code_change_to_change_payload():
    """CodeChange.to_change_payload() returns correct dict."""
    change = CodeChange(
        change_type="modify_file",
        file_path="src/agent.py",
        content="new content",
        old_content="old content",
        proposal_id="prop-0",
        proposal_summary="Modify agent",
        proposal_type="refactor",
        priority=2.5,
        estimated_lines=5,
    )
    payload = change.to_change_payload()
    assert payload["change_type"] == "modify_file"
    assert payload["file_path"] == "src/agent.py"
    assert payload["proposal_type"] == "refactor"
    assert payload["estimated_lines"] == 5


# ============================================================ code generation utilities

def t_generate_file_path():
    """generate_file_path produces plausible file paths."""
    path = generate_file_path("Add new agent feature", "new_file")
    assert path.endswith(".py")
    assert "src/" in path or "tests/" in path or "config/" in path
    
    path = generate_file_path("Update test suite", "new_file")
    assert "test" in path.lower() or path.endswith("_test.py")
    
    path = generate_file_path("Fix config bug", "modify_file")
    assert path.endswith(".py") or path.endswith(".yaml") or path.endswith(".json")


def t_generate_content():
    """generate_content produces non-empty content."""
    proposal = {
        "summary": "Add new feature",
        "description": "A new feature for testing",
        "evidence": "Test evidence",
        "source": "https://example.com",
    }
    
    content = generate_content(proposal, "new_file", "src/test.py")
    assert len(content) > 0
    assert "Add new feature" in content
    assert "https://example.com" in content
    
    content = generate_content(proposal, "modify_file", "src/agent.py")
    assert len(content) > 0
    assert "A new feature for testing" in content


def t_map_proposal_to_changes():
    """map_proposal_to_changes produces code change specs from proposals."""
    proposal = {
        "change_type": "feature",
        "summary": "Add new agent",
        "description": "A new agent implementation",
        "source": "https://github.com/example/new-agent",
        "evidence": "Example evidence",
        "priority": 3.0,
        "estimated_effort": 5,
    }
    
    changes = map_proposal_to_changes(proposal)
    assert len(changes) > 0
    assert all(isinstance(c, dict) for c in changes)
    assert all("change_type" in c for c in changes)
    assert all("file_path" in c for c in changes)
    assert all("content" in c for c in changes)


# ============================================================ code agent tests

def t_code_consumes_proposals():
    """Code agent consumes plan proposals from context."""
    # Run Review -> Plan to get proposals
    recs = review_agent.run("code-signoff-job-001")
    ctx = PipelineContext(job_id="code-signoff-job-001", review_recommendations=recs)
    proposals = plan_agent.run("code-signoff-job-001", ctx)
    
    # Set up context with proposals
    ctx.plan_proposals = proposals
    
    # Run Code
    changes = code_agent.run("code-signoff-job-001", ctx)
    
    assert len(changes) > 0, "expected at least some code changes"
    assert all(isinstance(c, CodeChange) for c in changes)


def t_code_fails_on_empty_input():
    """Code agent fails closed when given empty proposals."""
    ctx = PipelineContext(job_id="code-signoff-job-001")
    try:
        code_agent.run("code-signoff-job-001", ctx)
        raise AssertionError("should fail on empty input")
    except RuntimeError as e:
        assert "no plan proposals" in str(e)


def t_code_writes_changes_to_board():
    """Code agent writes all changes to the change board."""
    # Use unique job_id
    job_id = "code-write-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run(job_id, ctx)
    
    # Check change board has code_change entries for this job
    all_changes = bb.report(role="code", change_type="code_change")
    job_changes = [c for c in all_changes if c.get("job_id") == job_id]
    assert len(job_changes) == len(changes), \
        f"expected {len(changes)} code changes on board for {job_id}, got {len(job_changes)}"


def t_code_changes_have_priority():
    """Code changes have priority inherited from proposals."""
    recs = review_agent.run("code-signoff-job-001")
    ctx = PipelineContext(job_id="code-signoff-job-001", review_recommendations=recs)
    proposals = plan_agent.run("code-signoff-job-001", ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run("code-signoff-job-001", ctx)
    
    assert all(hasattr(c, 'priority') for c in changes)
    assert all(isinstance(c.priority, (int, float)) for c in changes)


def t_code_changes_have_file_paths():
    """Code changes have valid file paths."""
    recs = review_agent.run("code-signoff-job-001")
    ctx = PipelineContext(job_id="code-signoff-job-001", review_recommendations=recs)
    proposals = plan_agent.run("code-signoff-job-001", ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run("code-signoff-job-001", ctx)
    
    assert all(hasattr(c, 'file_path') for c in changes)
    assert all(c.file_path.endswith(('.py', '.md', '.yaml', '.yml', '.txt', '.json')) for c in changes)


def t_code_changes_have_content():
    """Code changes have non-empty content."""
    recs = review_agent.run("code-signoff-job-001")
    ctx = PipelineContext(job_id="code-signoff-job-001", review_recommendations=recs)
    proposals = plan_agent.run("code-signoff-job-001", ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run("code-signoff-job-001", ctx)
    
    assert all(hasattr(c, 'content') for c in changes)
    assert all(len(c.content) > 0 for c in changes)


# ============================================================ signoff_agent constants tests

def t_signoff_decisions_constant():
    """SIGN_OFF_DECISIONS contains expected decisions."""
    assert "accept" in SIGN_OFF_DECISIONS
    assert "reject" in SIGN_OFF_DECISIONS
    assert "hold_for_review" in SIGN_OFF_DECISIONS


def t_auto_accept_threshold():
    """AUTO_ACCEPT_THRESHOLD is set to expected value."""
    assert AUTO_ACCEPT_THRESHOLD == 0.95


def t_auto_hold_threshold():
    """AUTO_HOLD_THRESHOLD is set to expected value."""
    assert AUTO_HOLD_THRESHOLD == 0.70


# ============================================================ SignOffDecision dataclass

def t_signoff_decision_dataclass():
    """SignOffDecision is a valid dataclass with expected fields."""
    decision = SignOffDecision(
        decision="accept",
        rationale="All tests passed",
        test_results_count=10,
        passed_count=10,
        failed_count=0,
        held_count=0,
        critical_failures_count=0,
        job_id="test-job",
        change_ids=[1, 2, 3],
        priority=0,
    )
    assert decision.decision == "accept"
    assert decision.rationale == "All tests passed"
    assert decision.test_results_count == 10
    assert decision.passed_count == 10


def t_signoff_decision_to_change_payload():
    """SignOffDecision.to_change_payload() returns correct dict."""
    decision = SignOffDecision(
        decision="reject",
        rationale="Critical failures",
        test_results_count=5,
        passed_count=3,
        failed_count=2,
        held_count=0,
        critical_failures_count=1,
        job_id="test-job",
        change_ids=[1, 2],
    )
    payload = decision.to_change_payload()
    assert payload["decision"] == "reject"
    assert payload["rationale"] == "Critical failures"
    assert payload["failed_count"] == 2
    assert payload["critical_failures_count"] == 1


# ============================================================ decision logic

def t_calculate_decision_all_pass():
    """Decision is accept when all tests pass."""
    # Create mock test results (all passing)
    results = [
        TestResult(test_name="t1", category="unit", description="test", 
                  target_type="proposal", target_id="p1", target_summary="s1",
                  verdict="pass", detail="ok", priority=2),
        TestResult(test_name="t2", category="unit", description="test",
                  target_type="proposal", target_id="p2", target_summary="s2",
                  verdict="pass", detail="ok", priority=2),
    ]
    
    decision, rationale = calculate_decision(results)
    assert decision == "accept"
    assert "passing" in rationale.lower()


def t_calculate_decision_critical_failure():
    """Decision is reject when critical failures exist."""
    results = [
        TestResult(test_name="t1", category="unit", description="test",
                  target_type="proposal", target_id="p1", target_summary="s1",
                  verdict="pass", detail="ok", priority=2),
        TestResult(test_name="t2", category="security", description="test",
                  target_type="proposal", target_id="p2", target_summary="s2",
                  verdict="fail", detail="critical", priority=5),  # Critical failure
    ]
    
    decision, rationale = calculate_decision(results)
    assert decision == "reject"
    assert "critical" in rationale.lower()


def t_calculate_decision_low_pass_rate():
    """Decision is hold_for_review when pass rate is low."""
    results = [
        TestResult(test_name="t1", category="unit", description="test",
                  target_type="proposal", target_id="p1", target_summary="s1",
                  verdict="pass", detail="ok", priority=2),
        TestResult(test_name="t2", category="unit", description="test",
                  target_type="proposal", target_id="p2", target_summary="s2",
                  verdict="fail", detail="fail", priority=2),
        TestResult(test_name="t3", category="unit", description="test",
                  target_type="proposal", target_id="p3", target_summary="s3",
                  verdict="fail", detail="fail", priority=2),
    ]
    # Pass rate = 1/3 = 33% < 70%
    
    decision, rationale = calculate_decision(results)
    assert decision == "hold_for_review"
    assert "low" in rationale.lower() or "33" in rationale


def t_calculate_decision_empty():
    """Decision is hold_for_review when no test results."""
    decision, rationale = calculate_decision([])
    assert decision == "hold_for_review"
    assert "no test results" in rationale.lower()


# ============================================================ signoff agent tests

def t_signoff_consumes_test_results():
    """Sign off agent consumes test results from context."""
    # Use unique job_id
    job_id = "signoff-consume-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    # Run Review -> Plan -> Code -> Test to get test results
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run(job_id, ctx)
    ctx.code_changes = changes
    
    results = test_agent.run(job_id, ctx)
    ctx.test_results = results
    
    # Run Sign off
    decision = signoff_agent.run(job_id, ctx)
    
    assert isinstance(decision, SignOffDecision)
    assert decision.decision in SIGN_OFF_DECISIONS


def t_signoff_fails_on_empty_input():
    """Sign off agent fails closed when given empty test results."""
    ctx = PipelineContext(job_id="code-signoff-job-001")
    try:
        signoff_agent.run("code-signoff-job-001", ctx)
        raise AssertionError("should fail on empty input")
    except RuntimeError as e:
        assert "no test results" in str(e)


def t_signoff_writes_decision_to_board():
    """Sign off agent writes decision to the change board."""
    job_id = "signoff-write-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run(job_id, ctx)
    ctx.code_changes = changes
    
    results = test_agent.run(job_id, ctx)
    ctx.test_results = results
    
    decision = signoff_agent.run(job_id, ctx)
    
    # Check change board has signoff_decision entry for this job
    decisions = bb.report(role="signoff", change_type="signoff_decision")
    job_decisions = [d for d in decisions if d.get("job_id") == job_id]
    assert len(job_decisions) >= 1, "expected at least one signoff decision on board"


def t_signoff_decision_includes_counts():
    """Sign off decision includes test result counts."""
    job_id = "signoff-counts-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run(job_id, ctx)
    ctx.code_changes = changes
    
    results = test_agent.run(job_id, ctx)
    ctx.test_results = results
    
    decision = signoff_agent.run(job_id, ctx)
    
    assert decision.test_results_count == len(results)
    assert decision.passed_count + decision.failed_count + decision.held_count == len(results)


def t_signoff_marks_changes_accepted():
    """Sign off marks changes as accepted when decision is accept."""
    job_id = "signoff-accept-test-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    changes = code_agent.run(job_id, ctx)
    ctx.code_changes = changes
    
    results = test_agent.run(job_id, ctx)
    ctx.test_results = results
    
    decision = signoff_agent.run(job_id, ctx)
    
    # If decision is accept, check that changes are marked as accepted
    if decision.decision == "accept":
        accepted_changes = bb.report(outcome="accepted")
        job_accepted = [c for c in accepted_changes if c.get("job_id") == job_id]
        assert len(job_accepted) > 0, "expected accepted changes when decision is accept"


# ============================================================ pipeline integration

def t_pipeline_review_to_code():
    """Pipeline can run Review -> Plan -> Code sequence."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    pipeline.register_role("code", code_agent)
    
    bb.lock_job_spec("pipeline-code-001", SPEC)
    
    result = pipeline.run("pipeline-code-001", SPEC, start_role="review")
    
    assert result.success is True
    assert "review" in result.completed_roles
    assert "plan" in result.completed_roles
    assert "code" in result.completed_roles


def t_pipeline_full_sequence():
    """Pipeline can run complete Review -> Plan -> Code -> Test -> Sign off sequence."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    pipeline.register_role("code", code_agent)
    pipeline.register_role("test", test_agent)
    pipeline.register_role("signoff", signoff_agent)
    
    bb.lock_job_spec("pipeline-full-001", SPEC)
    
    result = pipeline.run("pipeline-full-001", SPEC, start_role="review")
    
    assert result.success is True
    assert "review" in result.completed_roles
    assert "plan" in result.completed_roles
    assert "code" in result.completed_roles
    assert "test" in result.completed_roles
    assert "signoff" in result.completed_roles


def t_pipeline_full_traces_all_steps():
    """Full pipeline execution is fully traced."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    pipeline.register_role("code", code_agent)
    pipeline.register_role("test", test_agent)
    pipeline.register_role("signoff", signoff_agent)
    
    bb.lock_job_spec("pipeline-full-trace-001", SPEC)
    
    result = pipeline.run("pipeline-full-trace-001", SPEC, start_role="review")
    
    # Check trace log for all role invocations
    all_events = [
        r["event_type"] for r in bb.conn.execute(
            "SELECT event_type FROM trace_log WHERE job_id='pipeline-full-trace-001'"
        )
    ]
    
    assert "pipeline_start" in all_events
    assert "pipeline_complete" in all_events
    assert "role_invoke" in all_events
    assert "model_response" in all_events


# ============================================================ manual sign off

def t_manual_sign_off_accept():
    """Manual sign off with accept decision works."""
    # Create a test job with some changes
    bb.lock_job_spec("manual-job-001", SPEC)
    
    # Create some dummy changes
    cid1 = bb.propose_change("manual-job-001", "test", "test_result", 
                              "Test 1", {"verdict": "pass"}, tier=3)
    cid2 = bb.propose_change("manual-job-001", "code", "code_change",
                              "Change 1", {"file": "test.py"}, tier=3)
    
    decision = signoff_agent.manual_sign_off(
        "manual-job-001", "accept", "Human approved all changes"
    )
    
    assert decision.decision == "accept"
    assert decision.rationale == "Human approved all changes"
    
    # Check changes are marked as accepted
    accepted = bb.report(outcome="accepted")
    accepted = [c for c in accepted if c.get("job_id") == "manual-job-001"]
    assert len(accepted) >= 2, "expected changes to be accepted"


def t_manual_sign_off_reject():
    """Manual sign off with reject decision works."""
    bb.lock_job_spec("manual-job-002", SPEC)
    
    # Create some dummy changes
    cid1 = bb.propose_change("manual-job-002", "test", "test_result",
                              "Test 1", {"verdict": "fail"}, tier=3)
    cid2 = bb.propose_change("manual-job-002", "code", "code_change",
                              "Change 1", {"file": "test.py"}, tier=3)
    
    decision = signoff_agent.manual_sign_off(
        "manual-job-002", "reject", "Human rejected due to failures"
    )
    
    assert decision.decision == "reject"
    
    # Check changes are marked as rejected
    rejected = bb.report(outcome="rejected")
    rejected = [c for c in rejected if c.get("job_id") == "manual-job-002"]
    assert len(rejected) >= 2, "expected changes to be rejected"


def t_manual_sign_off_invalid_decision():
    """Manual sign off rejects invalid decision values."""
    bb.lock_job_spec("manual-job-003", SPEC)
    
    try:
        signoff_agent.manual_sign_off("manual-job-003", "invalid", "test")
        raise AssertionError("should reject invalid decision")
    except ValueError as e:
        assert "invalid decision" in str(e)


# ============================================================ chain integrity

def t_chain_intact_after_code_signoff():
    """Hash chain remains intact after Code and Sign off execution."""
    ok, broken = bb.verify_chain()
    assert ok, f"chain broken at {broken}"


# ============================================================ run all tests

for name, fn in [
    # Code agent constants
    ("CODE_CHANGE_TYPES constant defined", t_code_change_types_constant),
    
    # CodeChange dataclass
    ("CodeChange dataclass works", t_code_change_dataclass),
    ("CodeChange.to_change_payload() works", t_code_change_to_change_payload),
    
    # Code generation utilities
    ("generate_file_path works", t_generate_file_path),
    ("generate_content works", t_generate_content),
    ("map_proposal_to_changes works", t_map_proposal_to_changes),
    
    # Code agent tests
    ("Code consumes proposals from context", t_code_consumes_proposals),
    ("Code fails on empty input", t_code_fails_on_empty_input),
    ("Code writes changes to change board", t_code_writes_changes_to_board),
    ("Code changes have priority", t_code_changes_have_priority),
    ("Code changes have file paths", t_code_changes_have_file_paths),
    ("Code changes have content", t_code_changes_have_content),
    
    # Sign off constants
    ("SIGN_OFF_DECISIONS constant defined", t_signoff_decisions_constant),
    ("AUTO_ACCEPT_THRESHOLD correct", t_auto_accept_threshold),
    ("AUTO_HOLD_THRESHOLD correct", t_auto_hold_threshold),
    
    # SignOffDecision dataclass
    ("SignOffDecision dataclass works", t_signoff_decision_dataclass),
    ("SignOffDecision.to_change_payload() works", t_signoff_decision_to_change_payload),
    
    # Decision logic
    ("calculate_decision: all pass -> accept", t_calculate_decision_all_pass),
    ("calculate_decision: critical failure -> reject", t_calculate_decision_critical_failure),
    ("calculate_decision: low pass rate -> hold", t_calculate_decision_low_pass_rate),
    ("calculate_decision: empty -> hold", t_calculate_decision_empty),
    
    # Sign off agent tests
    ("Sign off consumes test results", t_signoff_consumes_test_results),
    ("Sign off fails on empty input", t_signoff_fails_on_empty_input),
    ("Sign off writes decision to board", t_signoff_writes_decision_to_board),
    ("Sign off decision includes counts", t_signoff_decision_includes_counts),
    ("Sign off marks changes accepted", t_signoff_marks_changes_accepted),
    
    # Pipeline integration
    ("pipeline Review->Plan->Code works", t_pipeline_review_to_code),
    ("pipeline full sequence (all roles) works", t_pipeline_full_sequence),
    ("pipeline full sequence traces all steps", t_pipeline_full_traces_all_steps),
    
    # Manual sign off
    ("manual sign off: accept", t_manual_sign_off_accept),
    ("manual sign off: reject", t_manual_sign_off_reject),
    ("manual sign off: invalid decision", t_manual_sign_off_invalid_decision),
    
    # Chain integrity
    ("hash chain intact after code/signoff", t_chain_intact_after_code_signoff),
]:
    check(name, fn)


print(f"\nmodel mode: mock")
print(f"{len(passed)} passed, {len(failed)} failed")

# Print any failures
for name, error in failed:
    print(f"  FAILED: {name}: {error}")

sys.exit(1 if failed else 0)
