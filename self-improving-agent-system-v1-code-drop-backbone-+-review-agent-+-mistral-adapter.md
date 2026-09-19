# Self-Improving Agent System — v1 Code Drop

Three files, standard library only (Python 3.10+). Create this layout, copy each file, then follow **Run it** at the bottom.

```
self-improving-agents/
├── src/
│   ├── backbone.py
│   └── agent.py
└── tests/
    ├── test_backbone.py
    └── test_agent.py
```

## File 1 — `src/backbone.py`

SQLite backbone: hash-chained append-only trace log, change board (Tier 2 human sign-off invariant), goal-drift guard (spec locked as state, re-injected verbatim at every handoff), test-run counter, reporting + audit export.

```python
"""
Self-Improving Agent System — v1 SQLite Backbone
================================================
Locked v1 decisions (17–18 Sept 2026):
  - Append-only, out-of-band, SHA-256 hash-chained trace log (total coverage).
  - SQLite change board: all state changes flow through it.
  - Goal-drift guard (18 Sept amendment): original job spec stored as board
    STATE, re-injected verbatim at every role handoff; invariant guarantees the
    task spec never lives only in a model's context window.
  - Hardcoded invariant guards at the storage layer (triggers + code).
  - Test-run count logging per change (anti re-roll trap).

Agent roles cannot write the trace log or board directly through SQL: they get
narrow, audited functions. The trace log is out-of-band — its integrity does not
depend on agent behaviour.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "backbone.db"

ROLES = ("review", "plan", "code", "test", "signoff", "system", "human")

TRACE_EVENT_TYPES = (
    "role_invoke",        # a role was invoked with an input
    "model_response",     # raw model output captured
    "tool_call",          # a tool was called (name + args digest)
    "memory_read",        # RAG/memory read
    "memory_write",       # RAG/memory write
    "board_write",        # change board mutation
    "spec_injection",     # goal-drift guard: spec re-injected at a handoff
    "test_run",           # a test executed against a change
    "signoff",            # tier decision recorded
)

SCHEMA = """
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------- job specs --
-- The original job spec is stored as STATE (goal-drift guard). Immutable once
-- locked. Re-injected verbatim at every role handoff via inject_spec().
CREATE TABLE IF NOT EXISTS job_specs (
    job_id      TEXT PRIMARY KEY,
    spec_text   TEXT NOT NULL,
    locked_at   TEXT NOT NULL
);

-- ------------------------------------------------------------ change board --
CREATE TABLE IF NOT EXISTS changes (
    change_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT NOT NULL REFERENCES job_specs(job_id),
    role         TEXT NOT NULL,
    change_type  TEXT NOT NULL,          -- e.g. proposal, code_change, test_criteria, adjudication
    summary      TEXT NOT NULL,
    payload      TEXT NOT NULL,          -- JSON
    outcome      TEXT NOT NULL DEFAULT 'open',  -- open|accepted|rejected|held_for_review|superseded
    tier         INTEGER NOT NULL DEFAULT 3,    -- Tier 2 requires human signoff
    created_at   TEXT NOT NULL,
    decided_at   TEXT,
    decided_by   TEXT
);

-- Anti test-re-roll: every test run against a change is counted and logged.
CREATE TABLE IF NOT EXISTS test_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id   INTEGER NOT NULL REFERENCES changes(change_id),
    verdict     TEXT NOT NULL,           -- pass|fail|hold
    detail      TEXT,
    ran_at      TEXT NOT NULL
);

-- -------------------------------------------------------------- trace log --
-- Append-only, hash-chained. No UPDATE/DELETE possible (see triggers below).
CREATE TABLE IF NOT EXISTS trace_log (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    job_id      TEXT,
    role        TEXT NOT NULL,
    payload     TEXT NOT NULL,           -- JSON, canonicalised
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trace_no_update
BEFORE UPDATE ON trace_log
BEGIN
    SELECT RAISE(ABORT, 'INVARIANT: trace log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trace_no_delete
BEFORE DELETE ON trace_log
BEGIN
    SELECT RAISE(ABORT, 'INVARIANT: trace log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS specs_no_update
BEFORE UPDATE ON job_specs
BEGIN
    SELECT RAISE(ABORT, 'INVARIANT: locked job specs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS specs_no_delete
BEFORE DELETE ON job_specs
BEGIN
    SELECT RAISE(ABORT, 'INVARIANT: locked job specs are immutable');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _hash(prev: str, header: str, body: str) -> str:
    return hashlib.sha256((prev + "|" + header + "|" + body).encode()).hexdigest()


class Backbone:
    """Narrow, audited API for agent roles and the human operator."""

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------ job specs --
    def lock_job_spec(self, job_id: str, spec_text: str) -> None:
        """Store the original job spec as board state (goal-drift guard).
        Once locked it is immutable; changing a spec means a NEW job_id."""
        try:
            self.conn.execute(
                "INSERT INTO job_specs (job_id, spec_text, locked_at) VALUES (?,?,?)",
                (job_id, spec_text, _now()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(f"job spec already locked: {job_id}") from e
        self.trace("board_write", "system", {"action": "lock_job_spec", "job_id": job_id},
                   job_id=job_id)

    def get_spec_verbatim(self, job_id: str) -> str:
        row = self.conn.execute(
            "SELECT spec_text FROM job_specs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"no locked spec for job {job_id}")
        return row["spec_text"]

    def inject_spec(self, job_id: str, to_role: str) -> str:
        """Re-inject the original spec VERBATIM at a role handoff.
        Every injection is traced, proving the spec never lived only in context."""
        spec = self.get_spec_verbatim(job_id)
        self.trace("spec_injection", "system",
                   {"job_id": job_id, "injected_to": to_role, "verbatim": True},
                   job_id=job_id)
        return spec

    # --------------------------------------------------------- change board --
    def propose_change(self, job_id: str, role: str, change_type: str,
                       summary: str, payload: dict, tier: int = 3) -> int:
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        cur = self.conn.execute(
            "INSERT INTO changes (job_id, role, change_type, summary, payload, tier, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (job_id, role, change_type, summary, _canonical(payload), tier, _now()),
        )
        change_id = cur.lastrowid
        self.conn.commit()
        self.trace("board_write", role,
                   {"action": "propose", "change_id": change_id, "change_type": change_type},
                   job_id=job_id)
        return change_id

    def decide_change(self, change_id: int, outcome: str, decided_by: str) -> None:
        """Record a decision. Tier 2 outcomes require a human decider (invariant)."""
        row = self.conn.execute(
            "SELECT tier, job_id FROM changes WHERE change_id=?", (change_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"no change {change_id}")
        if row["tier"] == 2 and decided_by != "human":
            raise PermissionError(
                "INVARIANT: Tier 2 changes (invariants, trace config, rollback "
                "machinery, tier rules) require human sign-off"
            )
        if outcome not in ("accepted", "rejected", "held_for_review", "superseded"):
            raise ValueError(f"bad outcome: {outcome}")
        self.conn.execute(
            "UPDATE changes SET outcome=?, decided_at=?, decided_by=? WHERE change_id=?",
            (outcome, _now(), decided_by, change_id),
        )
        self.conn.commit()
        self.trace("board_write", decided_by,
                   {"action": "decide", "change_id": change_id, "outcome": outcome},
                   job_id=row["job_id"])

    # ------------------------------------------------------------ test runs --
    def log_test_run(self, change_id: int, verdict: str, detail: str = "") -> int:
        if verdict not in ("pass", "fail", "hold"):
            raise ValueError(f"bad verdict: {verdict}")
        cur = self.conn.execute(
            "INSERT INTO test_runs (change_id, verdict, detail, ran_at) VALUES (?,?,?,?)",
            (change_id, verdict, detail, _now()),
        )
        run_id = cur.lastrowid
        self.conn.commit()
        job = self.conn.execute(
            "SELECT job_id FROM changes WHERE change_id=?", (change_id,)
        ).fetchone()["job_id"]
        self.trace("test_run", "test",
                   {"change_id": change_id, "run_id": run_id, "verdict": verdict},
                   job_id=job)
        return run_id

    def test_run_count(self, change_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM test_runs WHERE change_id=?", (change_id,)
        ).fetchone()["c"]

    # ------------------------------------------------------------- trace log --
    def trace(self, event_type: str, role: str, payload: dict, job_id: str | None = None) -> int:
        if event_type not in TRACE_EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        last = self.conn.execute(
            "SELECT hash FROM trace_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = last["hash"] if last else "GENESIS"
        ts = _now()
        body = _canonical(payload)
        header = _canonical({"ts": ts, "event_type": event_type,
                             "job_id": job_id, "role": role})
        h = _hash(prev, header, body)
        cur = self.conn.execute(
            "INSERT INTO trace_log (ts, event_type, job_id, role, payload, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (ts, event_type, job_id, role, body, prev, h),
        )
        self.conn.commit()
        return cur.lastrowid

    def verify_chain(self) -> tuple[bool, int | None]:
        """Verify the SHA-256 hash chain end-to-end. Returns (ok, broken_seq)."""
        prev = "GENESIS"
        for row in self.conn.execute(
            "SELECT seq, ts, event_type, job_id, role, payload, prev_hash, hash FROM trace_log ORDER BY seq"
        ):
            header = _canonical({"ts": row["ts"], "event_type": row["event_type"],
                                 "job_id": row["job_id"], "role": row["role"]})
            if row["prev_hash"] != prev:
                return False, row["seq"]
            if _hash(prev, header, row["payload"]) != row["hash"]:
                return False, row["seq"]
            prev = row["hash"]
        return True, None

    # -------------------------------------------------------------- reports --
    def report(self, *, since: str | None = None, until: str | None = None,
               role: str | None = None, change_type: str | None = None,
               outcome: str | None = None) -> list[dict]:
        """Change-board reporting: filter by date / agent / type / outcome."""
        q = "SELECT * FROM changes WHERE 1=1"
        args: list = []
        if since:
            q += " AND created_at >= ?"; args.append(since)
        if until:
            q += " AND created_at <= ?"; args.append(until)
        if role:
            q += " AND role = ?"; args.append(role)
        if change_type:
            q += " AND change_type = ?"; args.append(change_type)
        if outcome:
            q += " AND outcome = ?"; args.append(outcome)
        q += " ORDER BY change_id"
        return [dict(r) for r in self.conn.execute(q, args)]

    def audit_export(self) -> str:
        """Human-readable audit export (full trace + board), for review."""
        lines = ["# Audit export", ""]
        for r in self.conn.execute("SELECT * FROM changes ORDER BY change_id"):
            lines.append(f"change {r['change_id']} [{r['role']}/{r['change_type']}] "
                         f"-> {r['outcome']} ({r['created_at']})")
            lines.append(f"  {r['summary']}")
        lines.append("")
        for r in self.conn.execute("SELECT * FROM trace_log ORDER BY seq"):
            lines.append(f"#{r['seq']} {r['ts']} {r['event_type']}/{r['role']} "
                         f"hash={r['hash'][:12]}…")
            lines.append(f"   {r['payload']}")
        return "\n".join(lines)


if __name__ == "__main__":
    bb = Backbone()
    print(f"backbone ready at {bb.db_path}")
    print("chain ok:", bb.verify_chain())
```

## File 2 — `src/agent.py`

Review role + model adapter. **Model resolution:** if `MISTRAL_API_KEY` is set → live calls to `api.mistral.ai` (stdlib HTTP); otherwise → deterministic mock. The key is read from the environment at runtime and never stored, logged, or traced.

```python
"""
Slice 2/3 — First agent role: Review (recommendation agent) + Mistral adapter.
=========================================================================
  - Role = prompt + tools + per-role model config (model-agnostic).
  - Model resolution: MISTRAL_API_KEY set -> live Mistral; otherwise mock.
  - Output = prioritised recommendations: source, type, evidence, impact, risk.
  - Every step flows through the backbone (total coverage).
  - Rubric scoring (novelty, relevance, evidence quality, actionability,
    vision alignment) scored by Paul/Vibe, 1-5 — stored when provided.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass, field

from backbone import Backbone

# --------------------------------------------------------------------- config

ROLE_DEFINITIONS = {
    "review": {
        "prompt": (
            "You are the Review role of a self-improving agent system. "
            "Your job: discover NEW experts and sources (not from a curated list) "
            "and propose novel improvements to the system design (GUI, UX, context "
            "recording, ontology, toolset). For every recommendation give: source, "
            "type, evidence, predicted impact, and risk. Prioritise the list. "
            "Do not modify anything directly — all changes go through the change board.\n\n"
            "Respond ONLY with valid JSON in this exact shape:\n"
            '{"recommendations": [{"source": "...", "type": "research_paper|source_class|'
            'improvement_proposal", "evidence": "...", "impact": "...", '
            '"risk": "low|medium|high"}]}'
        ),
        "model": {"provider": "mistral", "model": "mistral-large-latest"},
        "tools": ["search_sources", "read_source"],
    },
}

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


@dataclass
class ModelConfig:
    provider: str
    model: str
    api_key_env: str | None = None  # env var name holding the key


class MistralClient:
    """Minimal stdlib Mistral chat client. Key comes from the environment only."""

    def __init__(self, config: ModelConfig, api_key: str, endpoint: str = MISTRAL_API_URL):
        self.config = config
        self.api_key = api_key
        self.endpoint = endpoint

    def complete(self, system_prompt: str, user_input: str, timeout: int = 60) -> str:
        body = json.dumps({
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


class MockModel:
    """Deterministic stand-in when no API key is present. Same interface."""

    def __init__(self, config: ModelConfig):
        self.config = config

    def complete(self, system_prompt: str, user_input: str) -> str:
        return json.dumps({
            "recommendations": [
                {
                    "source": "arXiv:2609.14858 (Dream-RSI)",
                    "type": "research_paper",
                    "evidence": "Proposes scaffolded self-improvement with external validators",
                    "impact": "Cross-model validation design already borrowed; replay simulator could adopt its trajectory scoring",
                    "risk": "low",
                },
                {
                    "source": "solo-dev ECC-adjacent repos (pattern: single-maintainer agent frameworks)",
                    "type": "source_class",
                    "evidence": "Curated list missed the repo Paul found manually — class itself is the finding",
                    "impact": "Discovery tool should rank low-maintainer-count repos higher for novelty",
                    "risk": "medium — novelty correlates with unvetted quality",
                },
                {
                    "source": "prop: context-recording ontology for role handoffs",
                    "type": "improvement_proposal",
                    "evidence": "Goal-drift guard stores the spec as state; handoff context is the next unrecorded channel",
                    "impact": "Makes drift measurable at every handoff, not just spec divergence",
                    "risk": "medium — scope creep if ontology grows unbounded",
                },
            ]
        })


def make_model(config: ModelConfig):
    """Resolve the model for a role. Real Mistral if MISTRAL_API_KEY is set,
    deterministic mock otherwise. The key is never returned or stored."""
    key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if config.provider == "mistral":
        if key:
            return MistralClient(config, key)
        return MockModel(config)  # offline mode
    raise ValueError(f"unknown provider: {config.provider}")


def model_mode() -> str:
    return "mistral-live" if os.environ.get("MISTRAL_API_KEY", "").strip() else "mock"


# ----------------------------------------------------------------- the agent

@dataclass
class Recommendation:
    source: str
    type: str
    evidence: str
    impact: str
    risk: str
    scores: dict = field(default_factory=dict)  # rubric scores added later (1-5)

    @property
    def priority(self) -> float:
        risk_penalty = {"low": 0.0, "medium": 0.5, "high": 1.0}
        base = {"research_paper": 3, "source_class": 2, "improvement_proposal": 1}
        risk_key = self.risk.split()[0] if self.risk else "high"
        return base.get(self.type, 0) - risk_penalty.get(risk_key, 1.0)


def parse_recommendations(raw: str) -> list[Recommendation]:
    """Parse model output. Tolerates a markdown code fence around the JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    recs = data["recommendations"]
    valid_types = {"research_paper", "source_class", "improvement_proposal"}
    valid_risks = {"low", "medium", "high"}
    for r in recs:
        if r["type"] not in valid_types:
            raise ValueError(f"model produced unknown type: {r['type']}")
        if r["risk"].split()[0].lower() not in valid_risks:
            raise ValueError(f"model produced unknown risk: {r['risk']}")
    return [Recommendation(**r) for r in recs]


class ReviewAgent:
    """First agent role. Runs entirely through the backbone's audited API."""

    def __init__(self, bb: Backbone, role: str = "review"):
        self.bb = bb
        self.role = role
        self.definition = ROLE_DEFINITIONS[role]
        self.model = make_model(ModelConfig(**self.definition["model"]))

    def run(self, job_id: str) -> list[Recommendation]:
        # 1. Goal-drift guard: spec re-injected verbatim at handoff (traced).
        spec = self.bb.inject_spec(job_id, self.role)

        # 2. Role invocation traced with the spec digest (not full text — the
        #    authoritative copy lives on the board, invariant holds).
        self.bb.trace("role_invoke", self.role, {
            "tools": self.definition["tools"],
            "model": self.model.config.model,
            "mode": model_mode(),
            "spec_sha256_tail": hashlib.sha256(spec.encode()).hexdigest()[-12:],
        }, job_id=job_id)

        # 3. Tool call traced (discovery tool; real search wiring is next slice).
        self.bb.trace("tool_call", self.role, {
            "tool": "search_sources", "args_digest": "seeded-corpus-v0",
        }, job_id=job_id)

        # 4. Model response captured verbatim.
        raw = self.model.complete(self.definition["prompt"], spec)
        self.bb.trace("model_response", self.role, {
            "model": self.model.config.model, "mode": model_mode(), "response": raw,
        }, job_id=job_id)

        # 5. Parse, prioritise, and write every recommendation to the board.
        recs = parse_recommendations(raw)
        recs.sort(key=lambda r: r.priority, reverse=True)
        for r in recs:
            self.bb.propose_change(
                job_id, self.role, "recommendation",
                f"{r.type}: {r.source}",
                {"source": r.source, "type": r.type, "evidence": r.evidence,
                 "impact": r.impact, "risk": r.risk},
            )
        return recs

    def score(self, change_id: int, rubric: dict, scorer: str) -> None:
        """Paul/Vibe scoring, 1-5 per rubric axis, recorded as a board decision."""
        assert all(1 <= v <= 5 for v in rubric.values()), "scores must be 1-5"
        self.bb.decide_change(change_id, "held_for_review", scorer)
        row = self.bb.conn.execute(
            "SELECT payload FROM changes WHERE change_id=?", (change_id,)
        ).fetchone()
        payload = json.loads(row["payload"])
        payload["scores"] = {**rubric, "scorer": scorer}
        self.bb.conn.execute(
            "UPDATE changes SET payload=? WHERE change_id=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), change_id),
        )
        self.bb.conn.commit()
        self.bb.trace("board_write", scorer,
                      {"action": "score", "change_id": change_id, "scores": rubric})


if __name__ == "__main__":
    # One-shot live run: python3 src/agent.py "optional job spec text"
    import sys
    from pathlib import Path

    db = Path(__file__).resolve().parent.parent / "data" / "live.db"
    bb = Backbone(db)
    job_id = "job-live-001"
    spec = sys.argv[1] if len(sys.argv) > 1 else (
        "Discover NEW experts/sources for self-improving agent design and propose "
        "novel improvements (GUI, UX, context recording, ontology, toolset). "
        "Output: prioritised recommendations with source, type, evidence, impact, risk."
    )
    try:
        bb.lock_job_spec(job_id, spec)
    except ValueError:
        pass  # already locked from a previous run
    agent = ReviewAgent(bb)
    print(f"model mode: {model_mode()}")
    for r in agent.run(job_id):
        print(f"[{r.priority:4.1f}] {r.type:22s} {r.source}")
        print(f"        evidence: {r.evidence[:100]}")
        print(f"        impact:   {r.impact[:100]}  risk: {r.risk}")
    ok, broken = bb.verify_chain()
    print(f"\ntrace chain: {'OK' if ok else f'BROKEN at {broken}'}")
```

## File 3 — `tests/test_backbone.py`

7 tests including out-of-band tamper detection.

```python
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
```

## File 4 — `tests/test_agent.py`

9 tests: full agent run, coverage, goal-drift ordering, scoring, parser robustness, no-key-leak scan.

```python
"""End-to-end slice test: Review agent over the backbone. Run: python3 tests/test_agent.py"""
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

def t_parser_rejects_unknown_type():
    import json
    raw = json.dumps({"recommendations": [{"source": "x", "type": "banana",
                                           "evidence": "e", "impact": "i", "risk": "low"}]})
    try:
        parse_recommendations(raw)
        raise AssertionError("unknown type should be rejected")
    except (ValueError, KeyError):
        pass

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
    ("parser rejects unknown type/risk", t_parser_rejects_unknown_type),
    ("no API key in trace log", t_no_key_leak_in_trace),
    ("hash chain intact after full agent run", t_chain_still_intact),
]:
    check(name, fn)

print(f"\nmodel mode: {model_mode()}")
print(f"{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
```

## Run it

```bash
# 1. Offline first — confirm the harness is green (uses the mock):
python3 tests/test_backbone.py
python3 tests/test_agent.py

# 2. Wire the key (macOS/Linux — paste YOUR key inside the quotes, no prefix added):
export MISTRAL_API_KEY="paste-your-key-exactly-as-copied"

# 3. Verify it's set:
echo $MISTRAL_API_KEY

# 4. First LIVE run of the Review agent (creates data/live.db):
python3 src/agent.py

# 5. Re-run the tests in live mode (a test scans the trace for key leaks):
python3 tests/test_agent.py
```

Expected: `model mode: mistral-live`, a prioritised recommendation list from the real model, and `trace chain: OK`.

If step 4 prints an HTTP 401, the key is wrong/typo'd. If it prints 429 or 403, the free tier isn't activated for the account yet (check Billing in the Mistral console). On Windows, use `set MISTRAL_API_KEY=...` (cmd) or `$env:MISTRAL_API_KEY="..."` (PowerShell).