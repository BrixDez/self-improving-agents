"""
Slice 2/3 — First agent role: Review (recommendation agent) + Mistral adapter.
=========================================================================
  - Role = prompt + tools + per-role model config (model-agnostic).
  - Model resolution: MISTRAL_API_KEY set -> live Mistral; otherwise mock.
  - Output = prioritised recommendations: source, type, evidence, impact, risk.
  - Every step flows through the backbone (total coverage).
  - Rubric scoring (novelty, relevance, evidence quality, actionability,
    vision alignment) scored by Paul/Vibe, 1-5 — stored when provided.

v1.3 (19 Sept 2026): forced search grounding. Run 1 failed content
validation (1 clean citation of 10) because the Review role had no real
search tool — step 3 previously traced a DECORATIVE tool_call
('seeded-corpus-v0') for a search that never executed, so all citations
were model weights-recall. Changes in this version:
  1. Recommendation gains a 'url' field.
  2. Prompt now demands the evidence-pack URL as 'source'.
  3. run() phase 1: harness-driven grounding (search_grounding.ground) —
     the agent does NOT choose when to search (Paul's decision: keep the
     design tight, no wandering this early). Fail-closed: no evidence,
     no recommendations.
  4. run() phase 2: only recommendations whose 'source' exactly matches a
     pack URL reach the change board (parser-boundary enforcement).
  5. __main__ block defaults to job-live-002 with the SAME spec text as
     job-live-001 for the apples-to-apples trust-trend comparison.
  KEDB addition: traced-but-unimplemented tool calls are a honesty failure
  of the SYSTEM, not the model — only trace what actually executes.

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
from search_grounding import (
    evidence_pack_prompt,
    ground,
    validate_against_pack,
)

# --------------------------------------------------------------------- config

ROLE_DEFINITIONS = {
    "review": {
        "prompt": (
            "You are the Review role of a self-improving agent system. "
            "Your job: recommend experts and sources ONLY from the EVIDENCE "
            "PACK provided (found by live web search — never from memory) "
            "and propose novel improvements to the system design (GUI, UX, "
            "context recording, ontology, toolset). For every recommendation "
            "give: source (an exact URL from the evidence pack), type, "
            "evidence, predicted impact, and risk. Prioritise the list. "
            "Do not modify anything directly — all changes go through the change board.\n\n"
            "IMPORTANT constraints:\n"
            "- 'type' must be exactly one of: research_paper, source_class, "
            "improvement_proposal\n"
            "- 'risk' must be exactly one word: low, medium, or high\n"
            "- 'source' must be exactly one of the evidence-pack URLs\n"
            "- put any qualification in the evidence or impact fields\n\n"
            "Respond ONLY with valid JSON in this exact shape:\n"
            '{"recommendations": [{"source": "<exact evidence-pack URL>", "type": '
            '"research_paper|source_class|improvement_proposal", "evidence": "...", '
            '"impact": "...", "risk": "low|medium|high"}]}'
        ),
        "model": {"provider": "mistral", "model": "mistral-large-latest"},
        "tools": ["search_sources", "read_source"],  # executed by the harness
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
    """Deterministic stand-in when no API key is present. Same interface.
    v1.3: recommendations now use pack-style URLs so the grounded pipeline
    is exercised end-to-end in offline mode too."""

    def __init__(self, config: ModelConfig):
        self.config = config

    def complete(self, system_prompt: str, user_input: str) -> str:
        # Extract a pack URL to cite so mock runs pass pack validation.
        import re as _re
        urls = _re.findall(r"  (https?://\S+)", system_prompt)
        cite = urls[0] if urls else "https://arxiv.org/abs/2609.14858"
        return json.dumps({
            "recommendations": [
                {
                    "source": cite,
                    "type": "research_paper",
                    "evidence": "Proposes scaffolded self-improvement with external validators",
                    "impact": "Cross-model validation design already borrowed; replay simulator could adopt its trajectory scoring",
                    "risk": "low",
                },
                {
                    "source": "https://github.com/affaan-m/ECC",
                    "type": "source_class",
                    "evidence": "Solo-maintainer agent framework — the curated list missed this repo class",
                    "impact": "Discovery tool should rank low-maintainer-count repos higher for novelty",
                    "risk": "medium",
                },
                {
                    "source": "prop: context-recording ontology for role handoffs",
                    "type": "improvement_proposal",
                    "evidence": "Goal-drift guard stores the spec as state; handoff context is the next unrecorded channel",
                    "impact": "Makes drift measurable at every handoff, not just spec divergence",
                    "risk": "medium",
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
    url: str = ""             # v1.3: pack URL (== source when grounded)
    model_type: str = ""      # the type word the model actually used (pre-normalisation)
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
        src = r["source"]
        recs.append(Recommendation(
            source=src,
            type=canonical,
            evidence=r["evidence"],
            impact=r["impact"],
            risk=r["risk"],
            url=src if src.startswith("http") else "",
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

        # 3. PHASE 1 — forced grounding (harness-driven; the agent does not
        #    choose when to search). Fail-closed: raises before the model is
        #    consulted if no evidence can be gathered. Only real executions
        #    are traced — the v1 decorative 'seeded-corpus-v0' tool_call is
        #    gone (KEDB: traced-but-unimplemented tool calls).
        pack = ground(spec, self.bb, self.role, job_id)

        # 4. PHASE 2 — the model may only cite pack URLs. The evidence pack
        #    is appended to the system prompt; the spec is unchanged.
        prompt = self.definition["prompt"] + "\n\n" + evidence_pack_prompt(pack)
        raw = self.model.complete(prompt, spec)
        self.bb.trace("model_response", self.role, {
            "model": self.model.config.model, "mode": model_mode(),
            "response": raw, "pack_size": len(pack),
        }, job_id=job_id)

        # 5. Parse, enforce pack membership at the boundary, prioritise, and
        #    write ONLY accepted recommendations to the board.
        recs = parse_recommendations(raw)
        accepted, rejected = validate_against_pack(recs, pack)
        # traced as tool_call (the backbone whitelist has no 'pack_validation'
        # type — and shouldn't: this is an executed validation step, and the
        # specifics belong in the payload, not in a new Tier-2 event type)
        self.bb.trace("tool_call", self.role, {
            "tool": "pack_validation", "accepted": len(accepted),
            "rejected": len(rejected),
            "rejected_sources": [r.source[:120] for r in rejected],
        }, job_id=job_id)
        recs = accepted
        recs.sort(key=lambda r: r.priority, reverse=True)
        for r in recs:
            self.bb.propose_change(
                job_id, self.role, "recommendation",
                f"{r.type}: {r.source}",
                {"source": r.source, "type": r.type, "model_type": r.model_type,
                 "evidence": r.evidence, "impact": r.impact, "risk": r.risk,
                 "url": r.url},
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
    # v1.3: defaults to job-live-002 with the SAME spec as job-live-001.
    import sys
    from pathlib import Path

    db = Path(__file__).resolve().parent.parent / "data" / "live.db"
    bb = Backbone(db)
    job_id = "job-live-002"
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
    recs = agent.run(job_id)
    for r in recs:
        marker = "" if r.model_type == r.type else f"  (model said: {r.model_type})"
        print(f"[{r.priority:4.1f}] {r.type:22s} {r.source}{marker}")
        print(f"        evidence: {r.evidence[:100]}")
        print(f"        impact:   {r.impact[:100]}  risk: {r.risk}")
    ok, broken = bb.verify_chain()
    print(f"\ntrace chain: {'OK' if ok else f'BROKEN at {broken}'}")