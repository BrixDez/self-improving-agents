"""
Slice 2/3 — First agent role: Review (recommendation agent) + Mistral adapter.
=========================================================================
  - Role = prompt + tools + per-role model config (model-agnostic).
  - Model resolution: MISTRAL_API_KEY set -> live Mistral; otherwise mock.
  - Output = prioritised recommendations: source, type, evidence, impact, risk.
  - Every step flows through the backbone (total coverage).
  - Rubric scoring (novelty, relevance, evidence quality, actionability,
    vision alignment) scored by Paul/Vibe, 1-5 — stored when provided.

v1.2 (18 Sept 2026): second live-run failure — model invented the type
'source_expert' despite the enum in the prompt. Lesson locked in: you cannot
prompt your way to strict enums with a creative model; the PARSER is the
tolerant boundary. type is now normalised via a synonym map, and genuinely
unknown types fall back to 'improvement_proposal' (graded lowest-priority
class) with the model's original word preserved as model_type on the board.
Risk prose ('Medium: ...') handled the same way (v1.1).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
            "IMPORTANT constraints:\n"
            "- 'type' must be exactly one of: research_paper, source_class, "
            "improvement_proposal\n"
            "- 'risk' must be exactly one word: low, medium, or high\n"
            "- put any qualification in the evidence or impact fields\n\n"
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

# The three canonical types recommendations are graded against.
CANONICAL_TYPES = ("research_paper", "source_class", "improvement_proposal")

# Live-run synonyms observed or anticipated (extend as traces reveal more).
TYPE_SYNONYMS = {
    "research_paper": "research_paper",
    "paper": "research_paper",
    "study": "research_paper",
    "arxiv_paper": "research_paper",
    "research": "research_paper",
    "source_class": "source_class",
    "source_expert": "source_class",
    "expert_source": "source_class",
    "new_expert": "source_class",
    "expert": "source_class",
    "source": "source_class",
    "improvement_proposal": "improvement_proposal",
    "proposal": "improvement_proposal",
    "improvement": "improvement_proposal",
    "system_improvement": "improvement_proposal",
}


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


# ------------------------------------------------------------- normalisation

def _first_word_clean(text: str) -> str:
    """First word of a field, non-letters stripped, lowercased.
    'Medium: long explanation...' -> 'medium'. Empty -> ''."""
    if not text or not text.split():
        return ""
    return re.sub(r"[^a-z]", "", text.split()[0].lower())


def normalise_type(raw_type: str) -> tuple[str, bool]:
    """Map a model-produced type onto a canonical type.
    Returns (canonical_type, was_recognised).
    Known synonyms map cleanly; genuinely unknown words fall back to
    'improvement_proposal' (lowest-priority class) so a creative model never
    crashes the run — the original word is preserved as model_type."""
    key = re.sub(r"[^a-z_]", "", (raw_type or "").strip().lower())
    if key in TYPE_SYNONYMS:
        return TYPE_SYNONYMS[key], True
    return "improvement_proposal", False


# ----------------------------------------------------------------- the agent

@dataclass
class Recommendation:
    source: str
    type: str
    evidence: str
    impact: str
    risk: str
    model_type: str = ""     # the type word the model actually used (pre-normalisation)
    scores: dict = field(default_factory=dict)  # rubric scores added later (1-5)

    @property
    def priority(self) -> float:
        risk_penalty = {"low": 0.0, "medium": 0.5, "high": 1.0}
        base = {"research_paper": 3, "source_class": 2, "improvement_proposal": 1}
        risk_key = _first_word_clean(self.risk) or "high"
        return base.get(self.type, 0) - risk_penalty.get(risk_key, 1.0)


def parse_recommendations(raw: str) -> list[Recommendation]:
    """Parse model output. Tolerates a markdown code fence around the JSON,
    explanatory prose attached to constrained fields (v1.1), and invented
    type words (v1.2)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    recs_in = data["recommendations"]
    valid_risks = {"low", "medium", "high"}
    recs = []
    for r in recs_in:
        canonical, recognised = normalise_type(r.get("type", ""))
        risk_key = _first_word_clean(r.get("risk", ""))
        if risk_key not in valid_risks:
            # risk words we can't read at all: keep the prose, grade as high risk
            risk_key = "high"
        recs.append(Recommendation(
            source=r["source"],
            type=canonical,
            evidence=r["evidence"],
            impact=r["impact"],
            risk=r["risk"],
            model_type=r.get("type", ""),
        ))
    return recs


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
                {"source": r.source, "type": r.type, "model_type": r.model_type,
                 "evidence": r.evidence, "impact": r.impact, "risk": r.risk},
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
        marker = "" if r.model_type == r.type else f"  (model said: {r.model_type})"
        print(f"[{r.priority:4.1f}] {r.type:22s} {r.source}{marker}")
        print(f"        evidence: {r.evidence[:100]}")
        print(f"        impact:   {r.impact[:100]}  risk: {r.risk}")
    ok, broken = bb.verify_chain()
    print(f"\ntrace chain: {'OK' if ok else f'BROKEN at {broken}'}")