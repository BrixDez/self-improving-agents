"""Smoke test for the v1 backbone. Run: python3 tests/test_backbone.py"""
import sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from backbone import Backbone

passed, failed = [], []

def check(name, fn):
    try:
        fn(); passed.append(name); print(f"  ok  {name}")
    except Exception as e:
        failed.append((name, e)); print(f"FAIL  {name}: {e}")

tmp = Path(tempfile.mkdtemp())
bb = Backbone(tmp / "t.db")

SPEC = ("Job: build the first vertical slice. The agent must recommend NEW "
        "experts/sources and propose novel improvements. Output: prioritised "
        "recommendations with source, type, evidence, impact, risk.")

def t_spec_lock_and_inject():
    bb.lock_job_spec("job-001", SPEC)
    assert bb.get_spec_verbatim("job-001") == SPEC
    for role in ("review", "plan", "code"):
        assert bb.inject_spec("job-001", role) == SPEC

def t_spec_immutable():
    try:
        bb.conn.execute("UPDATE job_specs SET spec_text='tampered'")
        raise AssertionError("UPDATE should have been blocked")
    except sqlite3.DatabaseError as e:
        assert "append-only" in str(e) or "immutable" in str(e)
    assert bb.get_spec_verbatim("job-001") == SPEC

def t_change_flow():
    cid = bb.propose_change("job-001", "code", "code_change",
                            "add recommendation parser", {"file": "recs.py"})
    bb.log_test_run(cid, "fail", "first run fails")
    bb.log_test_run(cid, "pass", "fixed and re-run")
    assert bb.test_run_count(cid) == 2
    bb.decide_change(cid, "accepted", "human")

def t_tier2_needs_human():
    cid = bb.propose_change("job-001", "code", "invariant_change",
                            "relax trace coverage", {}, tier=2)
    try:
        bb.decide_change(cid, "accepted", "signoff")
        raise AssertionError("Tier 2 agent signoff should be blocked")
    except PermissionError:
        pass
    bb.decide_change(cid, "rejected", "human")

def t_trace_append_only():
    bb.trace("role_invoke", "plan", {"note": "planning"})
    try:
        bb.conn.execute("DELETE FROM trace_log WHERE seq=1")
        raise AssertionError("DELETE should have been blocked")
    except sqlite3.DatabaseError:
        pass

def t_tamper_detected():
    ok, broken = bb.verify_chain()
    assert ok, f"chain should be intact before tampering (broken at {broken})"
    # out-of-band tamper: attacker with raw DB access drops the guard trigger,
    # rewrites a payload row, restores the trigger — chain still catches it
    bb.conn.execute("DROP TRIGGER trace_no_update")
    bb.conn.execute("UPDATE trace_log SET payload='{\"evil\":true}' WHERE seq=1")
    bb.conn.execute(
        "CREATE TRIGGER trace_no_update BEFORE UPDATE ON trace_log "
        "BEGIN SELECT RAISE(ABORT, 'INVARIANT: trace log is append-only'); END"
    )
    bb.conn.commit()
    ok, broken = bb.verify_chain()
    assert not ok and broken == 1, f"tamper not detected (ok={ok}, broken={broken})"

def t_report_and_export():
    rows = bb.report(role="code", outcome="accepted")
    assert any(r["change_id"] == 1 for r in rows)
    ex = bb.audit_export()
    assert "Audit export" in ex and "spec_injection" in ex

for name, fn in [
    ("spec locked, verbatim re-injection traced", t_spec_lock_and_inject),
    ("locked spec is immutable (trigger)", t_spec_immutable),
    ("change flows through board; test runs counted", t_change_flow),
    ("Tier 2 requires human sign-off", t_tier2_needs_human),
    ("trace log append-only (trigger)", t_trace_append_only),
    ("hash chain detects tampering", t_tamper_detected),
    ("reporting filters + audit export", t_report_and_export),
]:
    check(name, fn)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)