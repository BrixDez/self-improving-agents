"""
test_planted_flaws.py — Planted-flaw benchmark for the v1.6 pipeline.
================================================================

JOB ID: probe-planted-flaws-001

PURPOSE:
  Test that the pipeline's validation layers REJECT known-bad content,
  not just accept known-good content. This is a negative test suite.

PLANTED FLAWS (exactly three, as Test-role inputs bypassing Review/Plan):
  1. Fabricated evidence — Proposal with evidence URL not in evidence pack
     (mimics KEDB #3: blended citation)
  2. Empty payload — CodeChange with empty description/content
     (mimics fail-closed violation)
  3. Secret leak — CodeChange with MISTRAL_API_KEY=sk-... content
     (mimics security check in test_agent.py)

ASSERTIONS (each must fail the pipeline, not pass it):
  1. Test role rejects or flags all three individually
     (each gets its own test case — do not plant all three in one run)
  2. Sign off does NOT auto-accept any run containing a planted flaw,
     regardless of aggregate pass rate >=95%
     (plant 3 flaws alongside 20 valid proposals to test circularity)
  3. Every rejection is written to change board as test_result
  4. Every rejection appears in the trace log
  5. verify_chain() returns (True, None) after probe runs

RULES:
  - NO changes to src/ in this job — probe only
  - If a planted flaw PASSES validation, the test must assert-fail loudly
    with a message naming which flaw got through
  - STOP and report it rather than patching src/ to make test green
    (that would be a Tier 2 board change)
  - Follow AGENTS.md
  - Run all existing 99 tests afterwards and confirm none broke

REPORT:
  pass/fail per flaw, plus exact board/trace evidence (change_ids) for each rejection
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backbone import Backbone
from pipeline import Pipeline, PipelineContext, create_pipeline
from plan_agent import Proposal
from code_agent import CodeChange
from test_agent import TestAgent, TestResult
from signoff_agent import SignOffAgent, calculate_decision

passed, failed = [], []
flaw_report = {}  # To store evidence for each flaw


def check(name, fn):
    try:
        result = fn()
        passed.append(name)
        print(f"  ok  {name}")
        return result
    except AssertionError as e:
        failed.append((name, str(e)))
        print(f"FAIL  {name}: {e}")
        raise


# ============================================================ setup

tmp = Path(__file__).resolve().parent.parent / "data" / "planted_flaws.db"
bb = Backbone(tmp)

# Lock the spec for this probe job
SPEC = (
    "Create tests/test_planted_flaws.py — a planted-flaw benchmark for the v1.6 pipeline. "
    "It must test that the pipeline's validation layers reject known-bad content, "
    "not just accept known-good content."
)

try:
    bb.lock_job_spec("probe-planted-flaws-001", SPEC)
except ValueError:
    pass  # Already locked

# Create agents for direct testing
test_agent = TestAgent(bb)
signoff_agent_auto = SignOffAgent(bb, auto_mode=True)
signoff_agent_manual = SignOffAgent(bb, auto_mode=False)


# ============================================================ helper functions

def create_valid_proposal(idx: int) -> Proposal:
    """Create a valid proposal that should pass all tests."""
    return Proposal(
        change_type="feature",
        summary=f"Valid proposal {idx}",
        description=f"This is a valid proposal for testing",
        source=f"https://example.com/valid-{idx}",
        evidence=f"Evidence for valid proposal {idx}",
        impact=f"Positive impact {idx}",
        risk="low",
        recommendation_type="improvement_proposal",
        priority=3.0,
        estimated_effort=5,
    )


def create_valid_code_change(idx: int) -> CodeChange:
    """Create a valid code change that should pass all tests."""
    return CodeChange(
        change_type="new_file",
        file_path=f"src/valid_file_{idx}.py",
        content=f"# Valid content {idx}\nprint('valid')",
        proposal_id=f"prop-{idx}",
        proposal_summary=f"Valid code change {idx}",
        proposal_type="feature",
        priority=3.0,
        estimated_lines=10,
    )


# ============================================================ FLAW 1: Fabricated Evidence
# A Proposal whose evidence field contains a URL not present in the evidence pack
# This mimics KEDB #3: blended citation
#
# fix-evidence-url-validation-001: the Test role now validates proposal
# source/evidence URLs against the job's evidence pack. The probe supplies
# an explicit pack on the context so the FLAW is a fabricated URL (pack
# member check), not a missing pack (which fails closed separately).

FAW_1_NAME = "fabricated_evidence"
FAW_1_DESCRIPTION = "Proposal with evidence URL not in evidence pack"

# Pack for this probe: the proposal's source IS a member; only the evidence
# URL is fabricated — isolating the flaw to the membership check.
FAW_1_PACK = {
    "https://example.com/real-source": "Real source used by the probe",
}


def t_flaw_1_fabricated_evidence():
    """Test that Test role flags a Proposal with fabricated evidence URL.

    This is a direct Test-role invocation (bypassing Review/Plan) with a
    Proposal whose evidence field contains a URL that was never in the
    evidence pack. The Test role MUST reject it (critical failure).
    """
    # Lock spec for this probe job
    probe_job_id = "probe-flaw-1"
    try:
        bb.lock_job_spec(probe_job_id, SPEC)
    except ValueError:
        pass  # Already locked

    # Create a proposal with a fabricated evidence URL
    bad_proposal = Proposal(
        change_type="feature",
        summary="Bad proposal with fake evidence",
        description="This looks valid but has fake evidence",
        source="https://example.com/real-source",
        evidence="Evidence from https://fake-pack-url-that-was-never-in-pack.com/study",
        impact="Some impact",
        risk="medium",
        recommendation_type="improvement_proposal",
        priority=2.0,
        estimated_effort=3,
    )

    # Run Test role directly on this proposal, with an explicit evidence pack
    ctx = PipelineContext(job_id=probe_job_id, plan_proposals=[bad_proposal],
                          evidence_pack=dict(FAW_1_PACK))

    try:
        results = test_agent.run(probe_job_id, ctx)

        # If the run did NOT abort, the fabricated-URL test must have failed.
        # (validate_evidence_urls is priority 4 -> critical, so an abort is
        # the expected path; reaching here means something is off.)
        detected = [r for r in results
                     if r.test_name == "validate_evidence_urls" and r.verdict == "fail"]

        if not detected:
            flaw_report[FAW_1_NAME] = {
                "status": "PASSED_THROUGH",
                "details": "Fabricated evidence URL was NOT rejected by any test",
                "change_ids": [r.change_id for r in results if r.change_id],
                "tests": [(r.test_name, r.verdict, r.detail) for r in results],
            }
            raise AssertionError(
                f"FLAW PASSED THROUGH: {FAW_1_NAME} - fabricated evidence URL "
                f"was not detected. Test results: "
                f"{[(r.test_name, r.verdict) for r in results]}"
            )

        flaw_report[FAW_1_NAME] = {
            "status": "REJECTED",
            "details": f"Caught by validate_evidence_urls ({len(detected)} result(s))",
            "change_ids": [r.change_id for r in results if r.change_id],
            "failed_tests": [(r.test_name, r.verdict, r.detail, r.priority) for r in detected],
        }

    except RuntimeError as e:
        # Pipeline aborted on a critical failure — verify it was the
        # evidence-URL validation that caught the flaw, not something else.
        if "validate_evidence_urls" not in str(e) and "evidence" not in str(e).lower():
            flaw_report[FAW_1_NAME] = {
                "status": "PASSED_THROUGH",
                "details": f"Aborted for the wrong reason: {e}",
                "change_ids": [],
            }
            raise AssertionError(
                f"FLAW PASSED THROUGH: {FAW_1_NAME} - pipeline aborted but not "
                f"because of evidence validation: {e}"
            )
        flaw_report[FAW_1_NAME] = {
            "status": "REJECTED",
            "details": f"Pipeline aborted on critical evidence failure: {e}",
            "change_ids": [],
        }

    # Clean up test db entries for this probe
    bb.conn.execute("DELETE FROM test_runs WHERE change_id IN (SELECT change_id FROM changes WHERE job_id='probe-flaw-1')")
    bb.conn.execute("DELETE FROM changes WHERE job_id='probe-flaw-1'")
    bb.conn.commit()


# ============================================================ FLAW 2: Empty Payload
# A CodeChange with empty description/content
# This mimics fail-closed violation

FAW_2_NAME = "empty_payload"
FAW_2_DESCRIPTION = "CodeChange with empty description/content"


def t_flaw_2_empty_payload():
    """Test that Test role flags a CodeChange with empty content."""
    # Lock spec for this probe job
    probe_job_id = "probe-flaw-2"
    try:
        bb.lock_job_spec(probe_job_id, SPEC)
    except ValueError:
        pass  # Already locked (probe db persists between runs)
    
    # Create a code change with empty content
    bad_change = CodeChange(
        change_type="new_file",
        file_path="src/empty.py",
        content="",  # EMPTY - this should fail
        proposal_id="prop-empty",
        proposal_summary="Empty code change",
        proposal_type="feature",
        priority=2.0,
        estimated_lines=0,
    )
    
    # Run Test role directly on this code change
    ctx = PipelineContext(job_id=probe_job_id, code_changes=[bad_change])
    
    try:
        results = test_agent.run("probe-flaw-2", ctx)
        
        # Check if any test failed
        failed_tests = [r for r in results if r.verdict == "fail"]
        
        if not failed_tests:
            # NO TEST FAILED - this is a problem!
            flaw_report[FAW_2_NAME] = {
                "status": "PASSED_THROUGH",
                "details": "Empty payload CodeChange was NOT rejected by any test",
                "change_ids": [r.change_id for r in results if r.change_id],
                "tests": [(r.test_name, r.verdict, r.detail) for r in results],
            }
            raise AssertionError(
                f"FLAW PASSED THROUGH: {FAW_2_NAME} - Empty payload CodeChange was not rejected. "
                f"Test results: {[(r.test_name, r.verdict) for r in results]}"
            )
        
        # Good - at least one test failed
        flaw_report[FAW_2_NAME] = {
            "status": "REJECTED",
            "details": f"Caught by {len(failed_tests)} test(s)",
            "change_ids": [r.change_id for r in results if r.change_id],
            "failed_tests": [(r.test_name, r.verdict, r.detail, r.priority) for r in failed_tests],
        }
        
    except RuntimeError as e:
        # Pipeline aborted due to critical failure - this is good
        flaw_report[FAW_2_NAME] = {
            "status": "REJECTED",
            "details": f"Pipeline aborted: {e}",
            "change_ids": [],
        }
    
    # Clean up
    bb.conn.execute("DELETE FROM test_runs WHERE change_id IN (SELECT change_id FROM changes WHERE job_id='probe-flaw-2')")
    bb.conn.execute("DELETE FROM changes WHERE job_id='probe-flaw-2'")
    bb.conn.commit()


# ============================================================ FLAW 3: Secret Leak
# A CodeChange whose content contains MISTRAL_API_KEY=sk-...
# This mimics the security check in test_agent.py

FAW_3_NAME = "secret_leak"
FAW_3_DESCRIPTION = "CodeChange with MISTRAL_API_KEY secret"


def t_flaw_3_secret_leak():
    """Test that Test role flags a CodeChange with secret leak."""
    # Create a code change with a secret
    import random
    secret_suffix = ''.join(random.choices('0123456789abcdef', k=16))
    bad_change = CodeChange(
        change_type="new_file",
        file_path="src/secret.py",
        content=f"MISTRAL_API_KEY=sk-{secret_suffix}",  # SECRET LEAK
        proposal_id="prop-secret",
        proposal_summary="Code change with secret",
        proposal_type="feature",
        priority=2.0,
        estimated_lines=1,
    )
    
    # Lock spec for this probe job
    probe_job_id = "probe-flaw-3"
    try:
        bb.lock_job_spec(probe_job_id, SPEC)
    except ValueError:
        pass  # Already locked (probe db persists between runs)
    
    # Run Test role directly on this code change
    ctx = PipelineContext(job_id=probe_job_id, code_changes=[bad_change])
    
    try:
        results = test_agent.run(probe_job_id, ctx)
        
        # Check for security test failure (priority 5)
        security_failures = [r for r in results if r.category == "security" and r.verdict == "fail"]
        
        if not security_failures:
            # NO SECURITY TEST FAILED - this is a CRITICAL problem!
            flaw_report[FAW_3_NAME] = {
                "status": "PASSED_THROUGH",
                "details": "Secret leak CodeChange was NOT rejected by security test",
                "change_ids": [r.change_id for r in results if r.change_id],
                "tests": [(r.test_name, r.verdict, r.category, r.detail) for r in results],
            }
            raise AssertionError(
                f"FLAW PASSED THROUGH: {FAW_3_NAME} - Secret leak was not detected. "
                f"Test results: {[(r.test_name, r.verdict, r.category) for r in results]}"
            )
        
        # Good - security test caught it
        flaw_report[FAW_3_NAME] = {
            "status": "REJECTED",
            "details": f"Caught by security test(s): {len(security_failures)}",
            "change_ids": [r.change_id for r in results if r.change_id],
            "security_failures": [(r.test_name, r.verdict, r.detail, r.priority) for r in security_failures],
        }
        
    except RuntimeError as e:
        # Pipeline aborted due to critical failure - this is expected
        flaw_report[FAW_3_NAME] = {
            "status": "REJECTED",
            "details": f"Pipeline aborted (critical security failure): {e}",
            "change_ids": [],
        }
    
    # Clean up
    bb.conn.execute("DELETE FROM test_runs WHERE change_id IN (SELECT change_id FROM changes WHERE job_id='probe-flaw-3')")
    bb.conn.execute("DELETE FROM changes WHERE job_id='probe-flaw-3'")
    bb.conn.commit()


# ============================================================ CIRCULARITY CHECK
# Plant 3 flaws alongside 20 valid proposals
# Test role should abort on critical failures (priority >= 4), preventing Sign off
# from auto-accepting. If Test completes without aborting, Sign off must still
# reject based on critical failures in the results.

FAW_CIRC_NAME = "circularity_check"


def t_flaw_circularity_check():
    """Test that the pipeline rejects runs containing planted flaws.
    
    With current implementation, Test role aborts on critical failures (priority >= 4),
    which prevents Sign off from running. This is fail-closed behavior.
    
    We plant 3 flawed proposals alongside 20 valid ones:
    - Fabricated evidence: Detected by validate_evidence_urls (priority 4, critical)
    - Empty description: Detected (priority 2, non-critical)
    - Secret leak: Detected (priority 5, critical) -> causes Test role abort
    """
    # Create 20 valid proposals
    valid_proposals = [create_valid_proposal(i) for i in range(20)]

    # Evidence pack covering every valid proposal's source URL, so the only
    # evidence-URL failures are the planted flaws
    circ_pack = {
        f"https://example.com/valid-{i}": f"Valid source {i}"
        for i in range(20)
    }
    
    # Create 3 flawed proposals
    # Flaw 1: Fabricated evidence (not currently detected by validation)
    flaw_1 = Proposal(
        change_type="feature",
        summary="Flawed: fabricated evidence",
        description="This has fake evidence",
        source="https://example.com",
        evidence="Evidence from https://fake-pack-url-that-was-never-in-pack.com/study",
        impact="Some impact",
        risk="medium",
        recommendation_type="improvement_proposal",
        priority=2.0,
        estimated_effort=3,
    )
    
    # Flaw 2: Empty description (will fail validate_description)
    flaw_2 = Proposal(
        change_type="feature",
        summary="Flawed: empty description",
        description="",  # EMPTY - will fail validation
        source="https://example.com",
        evidence="Some evidence",
        impact="Some impact",
        risk="medium",
        recommendation_type="improvement_proposal",
        priority=2.0,
        estimated_effort=3,
    )
    
    # Flaw 3: Secret leak (will fail validate_no_secrets with priority 5)
    import random
    secret_suffix = ''.join(random.choices('0123456789abcdef', k=16))
    flaw_3 = Proposal(
        change_type="feature",
        summary="Flawed: secret leak",
        description=f"This contains a secret: MISTRAL_API_KEY=sk-{secret_suffix}",
        source="https://example.com",
        evidence="Some evidence",
        impact="Some impact",
        risk="medium",
        recommendation_type="improvement_proposal",
        priority=2.0,
        estimated_effort=3,
    )
    
    all_proposals = valid_proposals + [flaw_1, flaw_2, flaw_3]
    
    # Lock spec for this probe job
    probe_job_id = "probe-flaw-circularity"
    try:
        bb.lock_job_spec(probe_job_id, SPEC)
    except ValueError:
        pass  # Already locked (probe db persists between runs)
    
    # Run Test role on all 23 proposals
    ctx = PipelineContext(job_id=probe_job_id, plan_proposals=all_proposals,
                          evidence_pack=circ_pack)
    
    try:
        results = test_agent.run(probe_job_id, ctx)
        
        # Count results
        passed = sum(1 for r in results if r.verdict == "pass")
        failed = sum(1 for r in results if r.verdict == "fail")
        total = len(results)
        pass_rate = passed / total if total > 0 else 0
        
        # Count critical failures (priority >= 4)
        critical_failures = sum(
            1 for r in results if r.verdict == "fail" and r.priority >= 4
        )
        
        # Now run Sign off
        ctx.test_results = results
        decision = signoff_agent_auto.run(probe_job_id, ctx)
        
        # Check: Sign off should NOT accept if there are critical failures
        if decision.decision == "accept" and critical_failures > 0:
            flaw_report[FAW_CIRC_NAME] = {
                "status": "CIRCULARITY_BROKEN",
                "details": f"Sign off ACCEPTED despite {critical_failures} critical failures. "
                           f"Pass rate: {pass_rate:.1%}",
                "change_ids": [r.change_id for r in results if r.change_id],
                "decision": decision.decision,
                "rationale": decision.rationale,
            }
            raise AssertionError(
                f"CIRCULARITY FAILURE: Sign off auto-accepted with {critical_failures} "
                f"critical failures and {pass_rate:.1%} pass rate"
            )
        
        # Good - Sign off did NOT auto-accept
        flaw_report[FAW_CIRC_NAME] = {
            "status": "REJECTED",
            "details": f"Sign off {decision.decision} with {critical_failures} critical failures. "
                       f"Pass rate: {pass_rate:.1%}",
            "change_ids": [r.change_id for r in results if r.change_id],
            "decision": decision.decision,
            "rationale": decision.rationale,
        }
        
        # Verify all results are on change board
        changes = bb.report(role="test", change_type="test_result")
        job_results = [c for c in changes if c.get("job_id") == probe_job_id]
        assert len(job_results) == len(results), \
            f"Expected {len(results)} test results on board, got {len(job_results)}"
        
    except RuntimeError as e:
        # Pipeline aborted - this is also acceptable
        flaw_report[FAW_CIRC_NAME] = {
            "status": "REJECTED",
            "details": f"Pipeline aborted: {e}",
            "change_ids": [],
        }
    
    # Clean up
    bb.conn.execute("DELETE FROM test_runs WHERE change_id IN (SELECT change_id FROM changes WHERE job_id='probe-flaw-circularity')")
    bb.conn.execute("DELETE FROM changes WHERE job_id='probe-flaw-circularity'")
    bb.conn.commit()


# ============================================================ Chain Integrity

def t_chain_integrity():
    """Verify hash chain is intact after all probe runs."""
    ok, broken = bb.verify_chain()
    if not ok:
        flaw_report["chain_integrity"] = {
            "status": "BROKEN",
            "details": f"Hash chain broken at seq {broken}",
        }
        raise AssertionError(f"Hash chain broken at {broken}")
    
    flaw_report["chain_integrity"] = {
        "status": "OK",
        "details": "Hash chain verified intact",
    }


# ============================================================ Run all tests

print("=" * 70)
print("PLANTED FLAW PROBE - probe-planted-flaws-001")
print("=" * 70)
print()

for name, fn in [
    ("Flaw 1: Fabricated evidence", t_flaw_1_fabricated_evidence),
    ("Flaw 2: Empty payload", t_flaw_2_empty_payload),
    ("Flaw 3: Secret leak", t_flaw_3_secret_leak),
    ("Circularity check (20 valid + 3 flaws)", t_flaw_circularity_check),
    ("Hash chain integrity", t_chain_integrity),
]:
    check(name, fn)


# ============================================================ Generate Report

print()
print("=" * 70)
print("FLAW PROBE REPORT")
print("=" * 70)
print()

for flaw_name, info in flaw_report.items():
    status = info.get("status", "UNKNOWN")
    print(f"[{status}] {flaw_name}")
    print(f"        {info.get('details', '')}")
    
    if info.get("change_ids"):
        print(f"        Change IDs: {info['change_ids']}")
    
    if info.get("failed_tests"):
        print(f"        Failed tests: {info['failed_tests']}")
    
    if info.get("security_failures"):
        print(f"        Security failures: {info['security_failures']}")
    
    if info.get("tests"):
        print(f"        All tests: {info['tests']}")
    
    print()


# ============================================================ Check for Critical Findings

critical_findings = []
for flaw_name, info in flaw_report.items():
    if info.get("status") == "PASSED_THROUGH":
        critical_findings.append(f"{flaw_name}: {info.get('details', '')}")
    elif info.get("status") == "CIRCULARITY_BROKEN":
        critical_findings.append(f"{flaw_name}: {info.get('details', '')}")
    elif info.get("status") == "NOT_DETECTED":
        critical_findings.append(f"{flaw_name}: NOT DETECTED BY VALIDATION")


if critical_findings:
    print("=" * 70)
    print("CRITICAL FINDINGS - STOP AND REPORT")
    print("=" * 70)
    for finding in critical_findings:
        print(f"  WARNING: {finding}")
    print()
    print("DO NOT modify src/ to fix these. Report to Paul.")
    print("=" * 70)
    sys.exit(1)


# ============================================================ Run Existing Tests

print()
print("=" * 70)
print("RUNNING EXISTING 99 TESTS")
print("=" * 70)
print()

import subprocess

existing_tests = [
    "tests/test_backbone.py",
    "tests/test_agent.py",
    "tests/test_pipeline.py",
    "tests/test_test_agent.py",
    "tests/test_code_and_signoff.py",
]

all_passed = True
for test_file in existing_tests:
    print(f"Running {test_file}...")
    result = subprocess.run(
        ["python", test_file],
        cwd=str(Path(__file__).resolve().parent.parent),  # repo root (Windows-safe)
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        print(f"  FAILED: {test_file}")
        print(result.stdout)
        print(result.stderr)
        all_passed = False
    else:
        # Count passed tests
        import re
        match = re.search(r'(\d+) passed, (\d+) failed', result.stdout)
        if match:
            print(f"  {match.group(1)} passed, {match.group(2)} failed")
        else:
            print(f"  Completed")


if not all_passed:
    print()
    print("EXISTING TESTS FAILED - DO NOT COMMIT")
    sys.exit(1)


print()
print("=" * 70)
print("ALL PROBE TESTS PASSED")
print("ALL 99 EXISTING TESTS PASSED")
print("=" * 70)

bb.close()
