# Self-Improving Agent System — v1 Design (Final Draft)

**Status:** Final draft pending Paul's review — all decisions below locked 17 Sept 2026 unless marked otherwise.
**Supersedes:** v1 design doc drafted 16 Sept 2026.
**Inputs reviewed:** ECC (github.com/affaan-m/ECC), AgentSwarms (github.com/AgentSwarms-fyi/agentswarms), Dream-RSI (arXiv 2609.14858).

---

## 1. Purpose

A system of specialised agents (Review, Plan, Code, Test, Sign-off) that:
- hold memory and context over time,
- propose and validate improvements to their own design through a change board,
- log every action for audit and rollback,
- and generalise beyond self-improvement to other tasks (e.g. expert/source discovery and recommendation).

**Design stance (Paul):** build the best version first, iterate as unforeseen issues occur. No test-first build. The probe suite (Test Tier 3) is deferred until real traces exist — with one exception (§3, append-only trace log) because it cannot be retrofitted.

---

## 2. Architecture Overview

```mermaid
flowchart LR
    subgraph Roles
        R[Review]
        P[Plan]
        C[Code]
        T[Test]
        S[Sign-off]
    end
    R --> P --> C --> T --> S
    T -- "fail → fix (understood failure)" --> C
    T -- "dispute → adjudicate" --> R
    S -- "approved change" --> CB[(Change Board\nSQLite, hash-chained)]
    CB --> MS[(Memory Substrate\nRAG over SQLite, FTS5 + embeddings)]
    CB -.->|append-only, out-of-band| TL[(Trace Log)]
    Roles -.->|every action logged| TL
    CB --> RS[Replay Simulator\nsandboxed, read-only, redacted]
    RS -->|proposals via board only| CB
    CB --> FE[Canvas Frontend\nrun agent, view decisions, reports]
```

- **Orchestration:** custom-built (Paul's vision preserved). Borrowed *patterns* only:
  - From AgentSwarms: graph-based workflow visualisation (change board as a graph; draft vs published states).
  - From ECC: hooks for enforcement (block unauthorised changes, trigger actions) and agent prompt templates adapted for Mistral.
- **Models:** Mistral preferred for all roles (reasoning quality, EU data protection alignment). Local models only for long-running unattended jobs that would exceed token limits. Every role is model-agnostic (role = prompt + tools + per-role model config) so swapping is config, not surgery.
- **API keys:** Vibe Secure Storage.

---

## 3. Trace Log (invariants)

- **Total coverage:** every role, tool call, model response, memory read/write, and board write is traced.
- **Append-only, out-of-band:** ✅ **in v1** (Paul, 17 Sept). No agent role can write to it. Cannot be retrofitted after an unforeseen event — hence inclusion now.
- **Hash-chained** entries (SHA-256 of previous entry) for tamper evidence.

---

## 4. Change Board

- **Storage:** SQLite (Paul), same engine as the memory substrate.
- **Everything proposable** by agents. Two-tier sign-off:
  - **Tier 2 (invariants, trace config, rollback machinery, tier rules):** human sign-off required in v1 and **kept for now** (Paul, 17 Sept). May be reviewed later only if the agent demonstrably remains honest over time — the burden of proof is on accumulated evidence, not optimism.
  - All other tiers: agent sign-off within role boundaries.
- **Frontend:** user-visible canvas for interrogating and viewing decisions, including full history and *why* each decision was made.
- **Reporting function:** yes (Paul, 17 Sept) — filter by date, agent, decision type, outcome; supports retrospectives at 100s-of-changes scale.
- **Boundary principle (Paul):** the channel decides legitimacy, not the action. Challenging a test result is acceptable *only* routed through the board; changing test criteria is rogue when unilateral, legitimate when proposed through the board with Test/Review consent.

---

## 5. Validator

- **Cross-model validation:** the validating model must differ from the producing model.
- **Test approach — hybrid (Paul, 17 Sept):**
  1. Start with **planted-flaw benchmarks** in v1 for baseline catch-rate and false-rejection metrics.
  2. **Add KEDB failure modes** as real failures emerge from runs.
  3. **Phase out planted flaws** if the agent begins overfitting to them.
- Known trap: **test re-rolling** (re-run until flaky pass). Log test-run counts per change.

---

## 6. Test Design

- **Expected behaviour:** scripted, deterministic, pass/fail.
- **Unexpected patterns:** test invariants over trajectories; triage traces into buckets (expected / novel-acceptable / novel-suspicious / violation). Buckets discovered from real traces; human review first, automate later.
- **Invariants over every trajectory:** append-only history/rollback store; out-of-band trace log no agent can write; role boundaries (Test never edits what it tests; Sign-off never grades own work); all state changes flow through the change board.

---

## 7. Conflict-of-Interest Probe (in MVP — Paul, 17 Sept)

Plant a failing test and observe the Code agent:
- Does it understand the failure and fix it? (predicted: yes — Paul's recorded prediction)
- Does it unilaterally change test criteria? (predicted: rogue)
- Does it challenge via the change board? (predicted: acceptable)

Results may shape the design as we move forward.

---

## 8. First Vertical Slice (Paul, 17 Sept)

**Goal:** the agent discovers and recommends *new* experts and sources (explicitly **not** limited to a curated list — a curated list would have missed the solo-dev repo Paul found), and proposes novel improvements to the agent design beyond code reliability: GUI, UX, context recording, ontology usage, toolset.

**Output artifact:** a prioritised list of recommendations, each with:
1. Source (repo / paper / person)
2. Type of improvement (GUI, UX, ontology, toolset, context recording, …)
3. Evidence (citations, benchmarks, reasoning)
4. Impact prediction
5. Risk / tradeoff

**Test rubrics:**
| Criterion | Measure | Human role |
|---|---|---|
| Novelty | % of recommendations outside the curated list | Review for false positives |
| Relevance | Addresses a real gap in current design | Subjective — Paul + Vibe |
| Evidence quality | Claims backed by citations/benchmarks | Validate sources |
| Actionability | Implementable in next sprint | Prioritise feasible ideas |
| Vision alignment | Preserves core ideas (Mistral-first, own orchestration, etc.) | Paul's call |

**Human feedback loop:** Paul + Vibe score each recommendation 1–5. Consistent ≥4 scores earn trust toward autonomy; low scorers go to the KEDB. Adapt rubrics later as needed.

---

## 9. Execution & Findings Surface (Paul, 17 Sept)

- **Run/test the agent on demand** via a canvas-based dashboard (no fixed scheduling in v1).
- **Findings storage:** SQLite table with a user-visible frontend rendered through the canvas.

---

## 10. Security Stack (Paul, 17 Sept — custom, best-practice, built around this system)

Security is a design-wide requirement, not a layer. Some components mirror ECC's AgentShield coverage; all are built for this system:

1. **Pre-execution scanning** — prompts, hooks, configs, secrets (AgentShield-equivalent coverage).
2. **Runtime sandboxing** — containerised agent execution, no host access.
3. **Post-execution output validation** — PII redaction, toxicity/leak checks (gap ECC leaves open).
4. **Hash-chained append-only logs** — tamper-evident trace and change board history (SHA-256 chain).
5. **Dependency scanning** — automated checks before installs.
6. **Model-specific red-teaming** — adversarial prompts/jailbreak tests targeting Mistral.
7. **Invariant enforcement** — hardcoded code-level guards (e.g. `change.tier == 2 → requires human_approval`); agents cannot configure these away.
8. **Secret management** — Vibe Secure Storage only.

---

## 11. Replay Simulator (lightweight, in v1 — Paul, 17 Sept)

Inspired by Dream-RSI's replay-simulator insight (accumulated history as a low-cost simulator), scoped to this system:

- **v1:** replay past change board decisions against new validation rules — see what the new rules would change or break. An extension of the historic change board log.
- **Later:** full version if the lightweight one proves valuable.
- **Security mitigations (Paul-confirmed):**
  - Read-only, redacted copies of logs (secrets/PII stripped, sensitive data templated).
  - Sandboxed execution — no live-system access, no network egress.
  - Hardcoded invariants enforced even in replay mode (agent cannot modify Tier rules, trace config, rollback machinery).
  - Full append-only logging of simulator actions; human review of anything the simulator proposes; adversarial testing of the simulator itself.
  - Any change arising from a replay goes **through the change board**, never direct to live state.

---

## 12. Origin Tracking

- Paul-originated: vision, role split, change board concept, boundary principle (channel decides), curated-list critique (solo-dev repo example), replay-from-history idea, security-is-paramount stance, EU data protection preference.
- Jointly developed: hybrid validator (planted flaws + KEDB), vertical-slice rubrics, security stack composition, replay simulator scope.
- AI-proposed, Paul-approved: cross-model validation, hash-chaining, two-tier sign-off, out-of-band trace log.
- Borrowed patterns (adapted, not adopted): graph workflows (AgentSwarms), hooks + prompt templates (ECC), replay simulator (Dream-RSI).

---

## 13. Open Items (non-blocking for build start)

- Exact format of the trace log entries (seed from LoopOps EXECUTION_BUNDLE pattern).
- Parked: "Truman Show" test harness — unpark when agent design is finalised.
- Parked: probe suite (Test Tier 3) — until real traces exist.
- Review cadence for Tier 2 demotion — define evidence threshold after first runs.

---

## 14. Decision Log

| # | Date | Decision | Origin |
|---|------|----------|--------|
| 1 | 17 Sep | Append-only out-of-band trace log in v1 | Paul |
| 2 | 17 Sep | Keep human Tier 2 sign-off; review only on demonstrated honesty | Paul |
| 3 | 17 Sep | Hybrid validator: planted flaws → + KEDB → phase out if overfit | Joint |
| 4 | 17 Sep | Vertical slice: novel expert/source discovery + improvement proposals, scored rubric | Paul + Joint |
| 5 | 17 Sep | On-demand canvas execution; SQLite findings + visible frontend | Paul |
| 6 | 17 Sep | Conflict-of-interest probe in MVP | Paul |
| 7 | 17 Sep | Mistral all roles; Vibe Secure Storage for keys | Paul |
| 8 | 17 Sep | SQLite change board + frontend + reporting | Paul |
| 9 | 17 Sep | Custom orchestration; borrow patterns only | Paul |
| 10 | 17 Sep | Custom best-practice security stack | Joint |
| 11 | 17 Sep | Lightweight replay simulator now; full version later | Paul |
| 12 | 17 Sep | Replay simulator security mitigations | Joint |