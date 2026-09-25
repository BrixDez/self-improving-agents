"""Tests for Test role. Run: python3 tests/test_test_agent.py

DEPENDENCIES:
  - src/backbone.py
  - src/agent.py
  - src/plan_agent.py
  - src/pipeline.py
  - src/test_agent.py
  - src/search_grounding.py
"""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backbone import Backbone
from agent import ReviewAgent
from plan_agent import PlanAgent, Proposal
from pipeline import Pipeline, PipelineContext, create_pipeline
from test_agent import TestAgent, TestResult, VERDICTS, TEST_CATEGORIES, CATEGORY_PRIORITY
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
bb = Backbone(tmp / "test_test_agent.db")

SPEC = (
    "Discover NEW experts/sources for self-improving agent design and propose "
    "novel improvements (GUI, UX, context recording, ontology, toolset). "
    "Output: prioritised recommendations with source, type, evidence, impact, risk."
)

# Lock spec for all tests
bb.lock_job_spec("test-job-001", SPEC)

# Create agents
review_agent = ReviewAgent(bb)
plan_agent = PlanAgent(bb)
test_agent = TestAgent(bb)


# ============================================================ constants tests

def t_verdicts_constant():
    """VERDICTS contains expected verdict values."""
    assert "pass" in VERDICTS
    assert "fail" in VERDICTS
    assert "hold" in VERDICTS


def t_test_categories_constant():
    """TEST_CATEGORIES contains expected category values."""
    expected = ["unit", "integration", "regression", "validation", "performance", "security"]
    assert all(cat in TEST_CATEGORIES for cat in expected)


def t_category_priority_mapping():
    """CATEGORY_PRIORITY has correct mappings."""
    assert CATEGORY_PRIORITY["security"] == 5
    assert CATEGORY_PRIORITY["regression"] == 4
    assert CATEGORY_PRIORITY["integration"] == 3
    assert CATEGORY_PRIORITY["unit"] == 2
    assert CATEGORY_PRIORITY["validation"] == 2
    assert CATEGORY_PRIORITY["performance"] == 1


# ============================================================ TestResult dataclass

def t_test_result_dataclass():
    """TestResult is a valid dataclass with expected fields."""
    result = TestResult(
        test_name="test_example",
        category="unit",
        description="Test description",
        target_type="proposal",
        target_id="prop-0",
        target_summary="Test proposal",
        verdict="pass",
        detail="Test passed",
        priority=3,
    )
    assert result.test_name == "test_example"
    assert result.category == "unit"
    assert result.verdict == "pass"
    assert result.priority == 3


def t_test_result_to_change_payload():
    """TestResult.to_change_payload() returns correct dict."""
    result = TestResult(
        test_name="test_example",
        category="validation",
        description="Test description",
        target_type="proposal",
        target_id="prop-0",
        target_summary="Test proposal",
        verdict="fail",
        detail="Test failed",
        priority=4,
    )
    payload = result.to_change_payload()
    assert payload["test_name"] == "test_example"
    assert payload["category"] == "validation"
    assert payload["verdict"] == "fail"
    assert payload["priority"] == 4


# ============================================================ test target extraction

def t_get_test_targets_from_proposals():
    """Test agent extracts targets from plan_proposals in context."""
    # Create some fake proposals
    proposals = [
        {"summary": "Proposal 1", "description": "Desc 1", "change_type": "feature"},
        {"summary": "Proposal 2", "description": "Desc 2", "change_type": "refactor"},
    ]
    
    ctx = PipelineContext(job_id="test-job-001", plan_proposals=proposals)
    targets = test_agent._get_test_targets(ctx)
    
    assert len(targets) == 2
    assert all(t["target_type"] == "proposal" for t in targets)
    assert targets[0]["target_id"] == "prop-0"
    assert targets[1]["target_id"] == "prop-1"


def t_get_test_targets_from_code_changes():
    """Test agent prefers code_changes over plan_proposals."""
    code_changes = [
        {"summary": "Code change 1", "description": "Change 1"},
    ]
    proposals = [
        {"summary": "Proposal 1", "description": "Prop 1"},
    ]
    
    ctx = PipelineContext(job_id="test-job-001", code_changes=code_changes, plan_proposals=proposals)
    targets = test_agent._get_test_targets(ctx)
    
    # Should prefer code_changes
    assert len(targets) == 1
    assert targets[0]["target_type"] == "code_change"


def t_get_test_targets_empty():
    """Test agent returns empty list when no targets available."""
    ctx = PipelineContext(job_id="test-job-001")
    targets = test_agent._get_test_targets(ctx)
    assert targets == []


# ============================================================ validation functions

def t_validate_change_type_valid():
    """Validation accepts known change types."""
    success, detail = test_agent._validate_change_type("feature")
    assert success is True
    assert "Valid" in detail
    
    success, detail = test_agent._validate_change_type("refactor")
    assert success is True


def t_validate_change_type_invalid():
    """Validation rejects unknown change types."""
    success, detail = test_agent._validate_change_type("banana")
    assert success is False
    assert "Unknown" in detail


def t_validate_non_empty():
    """Validation accepts non-empty strings."""
    success, detail = test_agent._validate_non_empty("some content", "field")
    assert success is True
    assert "present" in detail
    
    success, detail = test_agent._validate_non_empty("", "field")
    assert success is False
    assert "empty" in detail


def t_validate_effort():
    """Validation accepts reasonable effort estimates."""
    success, detail = test_agent._validate_effort(5)
    assert success is True
    
    success, detail = test_agent._validate_effort(0)
    assert success is False
    
    success, detail = test_agent._validate_effort(25)
    assert success is False


def t_validate_priority():
    """Validation accepts reasonable priority values."""
    success, detail = test_agent._validate_priority(3.5)
    assert success is True
    
    success, detail = test_agent._validate_priority(-10)
    assert success is False
    
    success, detail = test_agent._validate_priority(15)
    assert success is False


def t_validate_no_secrets():
    """Validation detects potential secrets."""
    # Test with suspicious patterns
    obj = {"api_key": "secret123", "name": "test"}
    success, detail = test_agent._validate_no_secrets(obj)
    assert success is False
    assert "secrets" in detail.lower()
    
    # Test with clean object
    obj = {"name": "test", "value": 123}
    success, detail = test_agent._validate_no_secrets(obj)
    assert success is True
    assert "No secrets" in detail


# ============================================================ evidence URL validation
# fix-evidence-url-validation-001

def t_extract_urls():
    """URL extraction finds http(s) URLs and strips trailing punctuation."""
    urls = test_agent._extract_urls(
        "See https://example.com/a, and https://example.com/b.")
    assert urls == ["https://example.com/a", "https://example.com/b"], urls
    assert test_agent._extract_urls("no urls here") == []
    assert test_agent._extract_urls(None) == []
    assert test_agent._extract_urls(12345) == []


def t_validate_evidence_urls():
    """Evidence URLs: pack members pass, fabricated URLs fail, no URLs pass."""
    pack = {"https://example.com/pack-source": "Pack source title"}

    # Cited URL is a pack member -> pass
    success, detail = test_agent._validate_evidence_urls(
        "https://example.com/pack-source",
        "Grounded in https://example.com/pack-source", pack)
    assert success is True, detail

    # Cited URL is NOT a pack member -> fail (KEDB #3: blended citation)
    success, detail = test_agent._validate_evidence_urls(
        "https://example.com/pack-source",
        "Evidence from https://fake-url-never-in-pack.com/study", pack)
    assert success is False, detail
    assert "not in evidence pack" in detail, detail

    # No URLs cited -> nothing to validate -> pass
    success, detail = test_agent._validate_evidence_urls(
        "", "plain prose evidence, no URL", pack)
    assert success is True, detail


def t_test_fails_closed_on_missing_pack():
    """Test agent fails closed when proposals exist but no evidence pack."""
    job_id = "test-missing-pack-001"
    bb.lock_job_spec(job_id, SPEC)

    proposal = Proposal(
        change_type="feature",
        summary="Proposal with no evidence pack",
        description="A structurally valid proposal",
        source="https://example.com/somewhere",
        evidence="Evidence text without any resolvable pack",
        impact="Some impact",
        risk="low",
        recommendation_type="improvement_proposal",
        priority=3.0,
        estimated_effort=5,
    )

    # No evidence_pack on the context and no board recommendations for
    # this job -> the Test role must abort, not skip the validation.
    ctx = PipelineContext(job_id=job_id, plan_proposals=[proposal])
    try:
        test_agent.run(job_id, ctx)
        raise AssertionError("expected fail-closed abort on missing evidence pack")
    except RuntimeError as e:
        assert "no evidence pack" in str(e).lower(), str(e)


# ============================================================ full test run

def t_test_consumes_proposals():
    """Test agent consumes plan proposals from context."""
    # Run Review -> Plan to get proposals
    recs = review_agent.run("test-job-001")
    ctx = PipelineContext(job_id="test-job-001", review_recommendations=recs)
    proposals = plan_agent.run("test-job-001", ctx)
    
    # Set up context with proposals
    ctx.plan_proposals = proposals
    
    # Run Test
    results = test_agent.run("test-job-001", ctx)
    
    assert len(results) > 0, "expected at least some test results"
    assert all(isinstance(r, TestResult) for r in results)


def t_test_fails_on_empty_input():
    """Test agent fails closed when given empty targets."""
    ctx = PipelineContext(job_id="test-job-001")
    try:
        test_agent.run("test-job-001", ctx)
        raise AssertionError("should fail on empty input")
    except RuntimeError as e:
        assert "no code changes or proposals" in str(e)


def t_test_writes_results_to_board():
    """Test agent writes all results to the change board."""
    # Use a fresh job_id to avoid interference
    job_id = "test-write-results-001"
    bb.lock_job_spec(job_id, SPEC)
    
    recs = review_agent.run(job_id)
    ctx = PipelineContext(job_id=job_id, review_recommendations=recs)
    proposals = plan_agent.run(job_id, ctx)
    ctx.plan_proposals = proposals
    
    results = test_agent.run(job_id, ctx)
    
    # Check change board has test_result entries for this job
    changes = bb.report(role="test", change_type="test_result")
    changes = [c for c in changes if c.get("job_id") == job_id]
    assert len(changes) == len(results), \
        f"expected {len(results)} test results on board for {job_id}, got {len(changes)}"


def t_test_logs_to_test_runs():
    """Test agent logs each test run to test_runs table."""
    # Get the count before
    initial_count = bb.test_run_count(1) if bb.report(role="test") else 0
    
    # Run tests
    recs = review_agent.run("test-job-001")
    ctx = PipelineContext(job_id="test-job-001", review_recommendations=recs)
    proposals = plan_agent.run("test-job-001", ctx)
    ctx.plan_proposals = proposals
    results = test_agent.run("test-job-001", ctx)
    
    # Each result should have a corresponding test_run
    for r in results:
        if r.change_id:
            count = bb.test_run_count(r.change_id)
            assert count >= 1, f"expected test_run for change {r.change_id}"


def t_test_results_have_verdicts():
    """All test results have valid verdicts."""
    recs = review_agent.run("test-job-001")
    ctx = PipelineContext(job_id="test-job-001", review_recommendations=recs)
    proposals = plan_agent.run("test-job-001", ctx)
    ctx.plan_proposals = proposals
    
    results = test_agent.run("test-job-001", ctx)
    
    assert all(r.verdict in VERDICTS for r in results)


def t_test_security_tests_highest_priority():
    """Security category tests have highest priority."""
    recs = review_agent.run("test-job-001")
    ctx = PipelineContext(job_id="test-job-001", review_recommendations=recs)
    proposals = plan_agent.run("test-job-001", ctx)
    ctx.plan_proposals = proposals
    
    results = test_agent.run("test-job-001", ctx)
    
    security_tests = [r for r in results if r.category == "security"]
    if security_tests:
        assert all(r.priority == 5 for r in security_tests)


# ============================================================ pipeline integration

def t_pipeline_review_to_test():
    """Pipeline can run Review -> Plan -> Test sequence."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    pipeline.register_role("test", test_agent)
    
    bb.lock_job_spec("pipeline-test-001", SPEC)
    
    result = pipeline.run("pipeline-test-001", SPEC, start_role="review")

    assert result.success is True
    assert "review" in result.completed_roles
    assert "plan" in result.completed_roles
    assert "test" in result.completed_roles
    # Review publishes the grounded evidence pack on the context, and it
    # survives the handoffs to Test (fix-evidence-url-validation-001)
    assert result.context.evidence_pack, "pipeline context should carry the evidence pack"


def t_pipeline_test_traces_all_steps():
    """Pipeline with Test role traces all steps."""
    pipeline = create_pipeline(bb)
    pipeline.register_role("review", review_agent)
    pipeline.register_role("plan", plan_agent)
    pipeline.register_role("test", test_agent)
    
    bb.lock_job_spec("pipeline-trace-test-001", SPEC)
    
    result = pipeline.run("pipeline-trace-test-001", SPEC, start_role="review")
    
    # Check trace log for test-specific events
    test_events = [
        r for r in bb.conn.execute(
            "SELECT * FROM trace_log WHERE job_id='pipeline-trace-test-001'"
        )
    ]
    
    event_types = [r["event_type"] for r in test_events]
    assert "role_invoke" in event_types
    assert any("test" in r["role"] for r in test_events)


# ============================================================ fail-closed behavior

def t_test_fails_on_critical_failure():
    """Test agent fails pipeline when critical test fails."""
    from plan_agent import Proposal
    
    # Create a proposal with a secret that will trigger a security test failure
    # Security tests have priority 5 (>= 4) so they will abort the pipeline
    bad_proposal = Proposal(
        change_type="feature",
        summary="Proposal with secret",
        description="This has api_key in it",
        source="https://example.com",
        evidence="test evidence",
        impact="test impact",
        risk="medium",
        recommendation_type="improvement_proposal",
        priority=3.0,
        estimated_effort=5,
    )
    
    ctx = PipelineContext(job_id="test-job-001", plan_proposals=[bad_proposal])
    
    try:
        # This should fail because security test will detect "api_key" and fail with priority 5
        test_agent.run("test-job-001", ctx)
        raise AssertionError("expected test to fail on critical security errors")
    except RuntimeError as e:
        # The error should mention critical test failures
        assert "critical test" in str(e).lower() or "failed" in str(e).lower()


# ============================================================ chain integrity

def t_chain_intact_after_test_run():
    """Hash chain remains intact after Test role execution."""
    ok, broken = bb.verify_chain()
    assert ok, f"chain broken at {broken}"


# ============================================================ run all tests

for name, fn in [
    # Constants
    ("VERDICTS constant defined", t_verdicts_constant),
    ("TEST_CATEGORIES constant defined", t_test_categories_constant),
    ("CATEGORY_PRIORITY mapping correct", t_category_priority_mapping),
    
    # TestResult dataclass
    ("TestResult dataclass works", t_test_result_dataclass),
    ("TestResult.to_change_payload() works", t_test_result_to_change_payload),
    
    # Target extraction
    ("extract targets from proposals", t_get_test_targets_from_proposals),
    ("prefer code_changes over proposals", t_get_test_targets_from_code_changes),
    ("empty targets returns empty list", t_get_test_targets_empty),
    
    # Validation functions
    ("validate_change_type (valid)", t_validate_change_type_valid),
    ("validate_change_type (invalid)", t_validate_change_type_invalid),
    ("validate_non_empty", t_validate_non_empty),
    ("validate_effort", t_validate_effort),
    ("validate_priority", t_validate_priority),
    ("validate_no_secrets", t_validate_no_secrets),
    ("extract_urls from text", t_extract_urls),
    ("validate_evidence_urls", t_validate_evidence_urls),
    
    # Full test run
    ("Test consumes proposals from context", t_test_consumes_proposals),
    ("Test fails on empty input", t_test_fails_on_empty_input),
    ("Test writes results to change board", t_test_writes_results_to_board),
    ("Test logs to test_runs table", t_test_logs_to_test_runs),
    ("Test results have valid verdicts", t_test_results_have_verdicts),
    ("Security tests have highest priority", t_test_security_tests_highest_priority),
    
    # Pipeline integration
    ("pipeline Review->Plan->Test works", t_pipeline_review_to_test),
    ("pipeline Test role traces all steps", t_pipeline_test_traces_all_steps),
    
    # Fail-closed behavior
    ("Test fails on critical validation failure", t_test_fails_on_critical_failure),
    ("Test fails closed on missing evidence pack", t_test_fails_closed_on_missing_pack),
    
    # Chain integrity
    ("hash chain intact after test", t_chain_intact_after_test_run),
]:
    check(name, fn)


print(f"\nmodel mode: mock")
print(f"{len(passed)} passed, {len(failed)} failed")

# Print any failures
for name, error in failed:
    print(f"  FAILED: {name}: {error}")

sys.exit(1 if failed else 0)
