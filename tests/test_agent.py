"""End-to-end slice test: Review agent over the backbone. Run: python3 tests/test_agent.py
v1.2 (18 Sept 2026): updated to the normalising-parser contract — invented type
words and risk prose no longer raise; they are normalised (or conservatively
defaulted) with the model's original wording preserved as model_type."""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from backbone import Backbone
from agent import ReviewAgent, parse_recommendations, model_mode

passed, failed = [], []

def check(name, fn):
    try:
        fn(); passed.append(name); print(f"  ok  {name}")
    except Exception as e:
        failed.append((name, e)); print(f"FAIL  {name}: {e}")

tmp = Path(tempfile.mkdtemp())
bb = Backbone(tmp / "t.db")
bb.lock_job_spec("job-001",
                 "Discover NEW experts/sources and propose novel improvements. "
                 "Output: prioritised recommendations (source, type, evidence, impact, risk).")
agent = ReviewAgent(bb)

def t_run_produces_board_changes():
    recs = agent.run("job-001")
    assert len(recs) >= 3
    assert all(recs[0].priority >= r.priority for r in recs)
    rows = bb.report(role="review", change_type="recommendation")
    assert len(rows) == len(recs)

def t_total_coverage_traced():
    types = {r["event_type"] for r in bb.conn.execute(
        "SELECT DISTINCT event_type FROM trace_log")}
    assert {"spec_injection", "role_invoke", "tool_call",
            "model_response", "board_write"} <= types

def t_spec_injected_before_role_invoke():
    seqs = list(bb.conn.execute(
        "SELECT seq, event_type FROM trace_log WHERE job_id='job-001' ORDER BY seq"))
    inj = next(s["seq"] for s in seqs if s["event_type"] == "spec_injection")
    inv = next(s["seq"] for s in seqs if s["event_type"] == "role_invoke")
    assert inj < inv, "spec must be injected before the role runs"

def t_scoring_recorded():
    cid = bb.report(role="review", change_type="recommendation")[0]["change_id"]
    agent.score(cid, {"novelty": 5, "relevance": 4, "evidence_quality": 3,
                      "actionability": 4, "vision_alignment": 5}, "human")
    import json
    payload = json.loads(bb.conn.execute(
        "SELECT payload FROM changes WHERE change_id=?", (cid,)).fetchone()["payload"])
    assert payload["scores"]["novelty"] == 5
    assert payload["scores"]["scorer"] == "human"

def t_score_bounds_enforced():
    cid = bb.report(role="review", change_type="recommendation")[1]["change_id"]
    try:
        agent.score(cid, {"novelty": 9}, "human")
        raise AssertionError("out-of-range score should be rejected")
    except AssertionError as e:
        if "out-of-range" in str(e): raise
    except Exception:
        pass

def t_parser_tolerates_code_fence():
    raw = '```json\n{"recommendations": [{"source": "x", "type": "research_paper", ' \
          '"evidence": "e", "impact": "i", "risk": "low"}]}\n```'
    recs = parse_recommendations(raw)
    assert recs[0].source == "x"

def t_parser_normalises_type_synonym():
    import json
    raw = json.dumps({"recommendations": [{"source": "x", "type": "source_expert",
                                           "evidence": "e", "impact": "i", "risk": "low"}]})
    recs = parse_recommendations(raw)
    assert recs[0].type == "source_class", "synonym should normalise to source_class"
    assert recs[0].model_type == "source_expert", "original model wording must be preserved"

def t_parser_unknown_type_falls_back():
    import json
    raw = json.dumps({"recommendations": [{"source": "x", "type": "banana",
                                           "evidence": "e", "impact": "i", "risk": "low"}]})
    recs = parse_recommendations(raw)
    assert recs[0].type == "improvement_proposal", "unknown type must fall back safely"
    assert recs[0].model_type == "banana"
    assert recs[0].priority <= 1.0, "fallback must not outrank known types"

def t_parser_strips_risk_prose():
    import json
    raw = json.dumps({"recommendations": [{"source": "x", "type": "research_paper",
                                           "evidence": "e", "impact": "i",
                                           "risk": "Medium: translating theory takes effort"}]})
    recs = parse_recommendations(raw)
    assert recs[0].priority == 2.5, "Medium prose must grade as medium risk (3.0 - 0.5)"

def t_parser_unreadable_risk_defaults_high():
    import json
    raw = json.dumps({"recommendations": [{"source": "x", "type": "research_paper",
                                           "evidence": "e", "impact": "i", "risk": "banana"}]})
    recs = parse_recommendations(raw)
    assert recs[0].priority == 2.0, "unreadable risk must conservatively grade as high (3.0 - 1.0)"

def t_no_key_leak_in_trace():
    import os
    key = os.environ.get("MISTRAL_API_KEY", "")
    if not key:
        return  # offline mode, nothing to leak
    for r in bb.conn.execute("SELECT payload FROM trace_log"):
        assert key not in r["payload"], "API key leaked into trace log!"

def t_chain_still_intact():
    ok, broken = bb.verify_chain()
    assert ok, f"chain broken at {broken}"

for name, fn in [
    ("agent run -> prioritised recommendations on the board", t_run_produces_board_changes),
    ("total coverage: all event types traced", t_total_coverage_traced),
    ("spec injected before role invocation (goal-drift guard order)", t_spec_injected_before_role_invoke),
    ("rubric scoring recorded on the board", t_scoring_recorded),
    ("score bounds (1-5) enforced", t_score_bounds_enforced),
    ("parser tolerates markdown code fence", t_parser_tolerates_code_fence),
    ("parser normalises type synonyms, preserves model_type", t_parser_normalises_type_synonym),
    ("parser falls back safely on unknown type", t_parser_unknown_type_falls_back),
    ("parser strips risk prose (v1.1 fix)", t_parser_strips_risk_prose),
    ("parser defaults unreadable risk to high (conservative)", t_parser_unreadable_risk_defaults_high),
    ("no API key in trace log", t_no_key_leak_in_trace),
    ("hash chain intact after full agent run", t_chain_still_intact),
]:
    check(name, fn)

print(f"\nmodel mode: {model_mode()}")
print(f"{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)