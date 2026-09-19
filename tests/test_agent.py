"""End-to-end slice test: Review agent over the backbone. Run: python3 tests/test_agent.py
v1.3 (19 Sept 2026): updated for forced search grounding (agent.py v1.3).
  - Offline deterministic search backend injected via set_search_backend()
    (tests must not depend on live websites — a flaky red erodes trust).
  - Boundary rejection is now visible by design: the mock model emits one
    non-pack source, so the run delivers 2 accepted + 1 rejected.
  - len(recs) >= 2 (was >= 3): the pipeline legitimately filters non-pack
    sources now; rejection itself is asserted in its own tests below.
v1.2 (18 Sept 2026): updated to the normalising-parser contract — invented type
words and risk prose no longer raise; they are normalised (or conservatively
defaulted) with the model's original wording preserved as model_type."""

import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from backbone import Backbone
from agent import ReviewAgent, parse_recommendations, model_mode
import search_grounding

# ---------------------------------------------------------- offline backend
# Deterministic fake search: same answers every run, no network. The pack
# the mock model can legitimately cite is exactly these three URLs.
FAKE_PACK = {
    "https://arxiv.org/abs/2607.13104": "Self-Improvements in Modern Agentic Systems: A Survey",
    "https://github.com/affaan-m/ECC": "affaan-m/ECC",
    "https://github.com/AgentSwarms-fyi/agentswarms": "AgentSwarms",
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

tmp = Path(tempfile.mkdtemp())
bb = Backbone(tmp / "t.db")
bb.lock_job_spec("job-001",
                 "Discover NEW experts/sources and propose novel improvements. "
                 "Output: prioritised recommendations (source, type, evidence, impact, risk).")
agent = ReviewAgent(bb)

def t_run_produces_board_changes():
    recs = agent.run("job-001")
    assert len(recs) >= 2, f"expected >= 2 accepted recommendations, got {len(recs)}"
    assert all(recs[0].priority >= r.priority for r in recs)
    rows = bb.report(role="review", change_type="recommendation")
    assert len(rows) == len(recs), "every ACCEPTED recommendation must be on the board"
    # every accepted source must be a pack URL (grounding invariant)
    for r in recs:
        assert r.source in FAKE_PACK, f"non-pack source reached the board: {r.source}"

def t_boundary_rejects_non_pack_sources():
    from agent import Recommendation
    pack = dict(FAKE_PACK)
    recs = [
        Recommendation(source="https://arxiv.org/abs/2607.13104", type="research_paper",
                       evidence="e", impact="i", risk="low"),
        Recommendation(source="https://arxiv.org/abs/2607.13104x", type="research_paper",
                       evidence="e", impact="i", risk="low"),   # near-miss URL
        Recommendation(source="prop: context-recording ontology", type="improvement_proposal",
                       evidence="e", impact="i", risk="medium"),  # not a URL at all
    ]
    accepted, rejected = search_grounding.validate_against_pack(recs, pack)
    assert len(accepted) == 1 and accepted[0].source.endswith("13104")
    assert len(rejected) == 2, "near-miss and non-URL sources must both be rejected"

def t_fail_closed_on_empty_pack():
    # A backend that returns nothing -> ground() must refuse to run phase 2.
    import agent as agent_mod
    search_grounding.set_search_backend(lambda q: [])
    tmp2 = Path(tempfile.mkdtemp())
    bb2 = Backbone(tmp2 / "t2.db")
    bb2.lock_job_spec("job-002", "Discover NEW experts/sources.")
    agent2 = ReviewAgent(bb2)
    try:
        agent2.run("job-002")
        raise AssertionError("empty evidence pack must abort the run")
    except RuntimeError as e:
        assert "no evidence" in str(e).lower()
    finally:
        search_grounding.set_search_backend(_fake_search)  # restore for later tests

def t_searches_traced_as_tool_calls():
    # Grounding must be visible in the trace: web searches ARE tool calls.
    types = {r["event_type"] for r in bb.conn.execute(
        "SELECT DISTINCT event_type FROM trace_log")}
    assert {"spec_injection", "role_invoke", "tool_call",
            "model_response", "board_write"} <= types
    # and the tool_call payloads must mention web_search
    tools = [r["payload"] for r in bb.conn.execute(
        "SELECT payload FROM trace_log WHERE event_type='tool_call'")]
    assert any("web_search" in p for p in tools), "searches must be traced as tool calls"

def t_pack_validation_traced():
    rows = list(bb.conn.execute(
        "SELECT payload FROM trace_log WHERE event_type='board_write'"))
    # pack_validation is traced via the role's own trace entry; simplest check:
    # the model_response trace records the pack size
    mr = list(bb.conn.execute(
        "SELECT payload FROM trace_log WHERE event_type='model_response'"))
    assert any('"pack_size"' in r["payload"] for r in mr), "pack size must be traced"

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
    cids = bb.report(role="review", change_type="recommendation")
    assert len(cids) >= 2, "scoring bounds test needs >= 2 board recommendations"
    cid = cids[1]["change_id"]
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
    ("pack boundary rejects non-pack and near-miss sources", t_boundary_rejects_non_pack_sources),
    ("fail-closed: empty evidence pack aborts the run", t_fail_closed_on_empty_pack),
    ("total coverage: all event types traced", t_searches_traced_as_tool_calls),
    ("pack size recorded in model_response trace", t_pack_validation_traced),
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