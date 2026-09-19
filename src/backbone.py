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