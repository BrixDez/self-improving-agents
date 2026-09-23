# Validation Session Log — 23 Sept 2026

> **How to use:** Save this file as `docs/validation/validation-session-log-2026-09-23.md` in the repo, then `git add docs/validation` → `git commit -m "Add validator session log (23 Sept)"` → `git push`.

---

## Purpose

First full run of the cross-model validator exercise: an independent review of the v1 design and prototype evidence, used to pressure-test our own diagnosis before writing the v2 PRD. Method: identical evidence-only input pack, our causal theory withheld, two different model families, predictions recorded before reading outputs.

## Input pack

- File: `docs/validation/validator-prompt.md`
- Contents: v1 design doc (read from disk, not duplicated), raw evidence from runs 1–3 (verbatim facts, no interpretation), the 5 finalised KEDB failure modes, known open gaps, six structured questions, output constraints including mandatory `[judgement — unsupported]` labelling.
- Withheld on purpose (in a separate file, never fed to any session): our causal theory — "orchestration proven; content validation and a real Code role are what's missing."

## Runs

| Run | Surface | Model | Output file |
|---|---|---|---|
| 1 | Mistral Vibe CLI v2.25.5 | Mistral Medium 3.5 [high] | `validator-output-mistralmed3.md` |
| 2 | Same CLI, model switched | GLM 5.2 | `validator-output-glm52.md` |

Note: a true cross-family comparison (Mistral vs GLM), not the weak web-vs-CLI same-family pairing flagged earlier.

## Prediction (Paul, recorded before reading run 1)

That the validator's #1 ranked weakness would be **Test-role circularity** (over the content-validation gap). Outcome: **confirmed twice** — both models ranked circularity first, with the identical top-3 ordering. Prediction record now three-for-three counting the planted-flaw probe.

## Findings

**Convergence (both models, same evidence, no shared theory):**
- Identical top-3 weaknesses: (1) Test-role circularity, (2) claim-level validation gap, (3) evidence-pack retrieval fragility.
- Both challenged the same locked sections: §5 (Validator) and §6 (Test Design); both held §3 (trace log) and §4 (change board) as unchallenged.
- Both predicted the same dominant future failure: **silent claim fabrication behind real URLs** — embellished figures/wrong attribution on genuine, resolvable sources, which passes every current automated check.
- Both proposed the same cheap probe: a **nightly claim-URL reconciliation script** (fetch cited URLs, string-match recommendation evidence text against source content, flag mismatches).
- Both proposed the same circularity fix shape: separate artifact execution from artifact evaluation (sandbox-execute Code output), automate both.

**Additions beyond our theory:**
- Measurable baseline: the planted-flaw probe's catch rate is **1 of 3 flaw types (33%)** — a concrete starting line for v2 (GLM).
- New trust criterion: **zero KEDB additions over a 100-run window** — self-funding (KEDB entries are already observable), unlike post-hoc audit metrics (GLM). Mistral's "zero undetected fabrications" metric quietly required an unfunded audit — flagged as such.
- Rule-vs-enforcement gap: fail-closed on empty payloads exists as a rule but was not enforced by the Test role (GLM).
- KEDB is finalised but not wired into automated checks — v2 backlog item (GLM).

**Skepticism retained:**
- Both models glossed the difficulty of claim-vs-source matching (legitimate paraphrase, pages changed since fetch, figures restated). The reconciliation probe needs a tolerance policy — an unresolved design decision, Paul's call.
- Convergence on diagnosis is strong; convergence on prescription is weaker (similar training-corpus reflexes). The probe adjudicates.

## Trust-trend data points (cumulative)

1. Run 1 (ungrounded): 1/10 clean citations — fabrication baseline.
2. Run 2 (grounded): 10/10 real URLs — grounding works; claims still unverified.
3. Planted-flaw probe: boundary respected, chain intact, Sign-off math holds; detection gaps at Test role (33% catch rate).
4. **Validator exercise (this session):** two independent model families converge with our own diagnosis and with Paul's recorded prediction; withheld theory confirmed; no fabrication observed in either output (each used `[judgement — unsupported]` correctly where reasoning lacked evidence).

## Decisions & backlog items arising

- **Claim-URL reconciliation probe** promoted to v2 build candidate (double-nominated independently). Next open design call before spec: strict exact-string matching (more catches, false alarms on paraphrase) vs similarity threshold (fewer false alarms, trusts a score). Paul to decide.
- Wire KEDB into automated checks (backlog).
- Evidence-pack rate-limit retry/backoff + query-shape assertion test (backlog, both models ranked third).
- Human oversight reduction criteria: adopt GLM's metric set (95% planted-flaw detection across all types, 100% claim-URL reconciliation, rubric mean ≥4.0 with no score <3, one test-run per change, chain verified, zero KEDB additions — sustained over 100 non-placeholder runs).

## Status ladder (honest)

- Diagnosis: **demonstrated** (three-way convergence, prediction confirmed).
- Solutions (sandbox execution, reconciliation probe): **plausible design** — nothing built, nothing run.
- Trust in the system's outputs: improved but conditional on closing the two gaps above.