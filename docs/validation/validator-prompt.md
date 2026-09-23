# Validator Input Pack — v2 PRD Review

> **How to use:** Save this file as `docs/validation/validator-prompt.md` in the repo root working copy. Then run it from your plain terminal (not inside an agent session you're trusting) via the Mistral CLI:
> `vibe` → *"Read docs/validation/validator-prompt.md and the design doc it references. Answer its questions in full. Do not modify any files."*
> Save the transcript to `docs/validation/validator-output-glm.md` before reading it.
> **Do not** paste the withheld theory file into the same session.

---

## Role

You are an independent systems reviewer. You are reviewing the design of a multi-agent system and the evidence from its first prototype runs. You did not build it. Be candid — a review that flatters the design is worthless. If you think a core decision is wrong, say so and say why.

## Context to read first

Read the file `self-improving-agent-system-v1-design-final-draft.md` in this directory. That is the v1 design (locked 17 Sept 2026). Then read `AGENTS.md` for the operating rules the prototype runs under.

## Raw evidence from prototype runs (Sept 2026)

The following is what actually happened, reported as fact. No interpretation is offered.

**Implementation state.** ~3,800 LOC, 99 tests green locally. Five roles (Review, Plan, Code, Test, Sign-off) orchestrated by `src/pipeline.py`. Backbone: SQLite, hash-chained append-only trace log (triggers block UPDATE/DELETE; tamper test proves detection), change board with Tier 2 human sign-off invariant, goal-drift guard (spec locked immutable, re-injected verbatim at every handoff), test-run counter (anti re-roll). The Code role generates deterministic placeholder code with no LLM; changes are not applied to the filesystem.

**Run 1 (ungrounded).** Review role ran live (mistral-large-latest) with no search tool wired. Its prompt declared tools `["search_sources", "read_source"]`, but the code only traced a fake tool call — no search was ever executed. Output: 10 recommendations written to the change board, trace chain OK. Human scoring: only 1 of 10 had a clean citation (and its summary was useless). Every other real source arrived with fabricated or embellished specifics; 4 were unvalidatable (fabricated figures). 13 "ghost" recommendations from this run remain on the board.

**Run 2 (grounded).** Forced search sequence added (harness-driven, deterministic queries from the locked spec, max 4 searches, fail-closed on empty evidence pack). Model may recommend only from the retrieved evidence pack; URL membership enforced at the parser boundary. Result: 10/10 recommendations with real, verifiable source URLs. Trace chain OK. Caveat: grounded URLs ≠ grounded claims — the agent's prose *describing* those sources has not yet been spot-checked against repo reality.

**Planted-flaw probe (run 3).** 20 valid + 3 flawed proposals injected. Results: fabricated evidence URLs NOT detected (gap); empty payloads NOT detected (gap); secret leaks DETECTED. Circularity check held — the pipeline aborted on critical failure, chain intact, 99 tests unbroken. So the Sign-off aggregation has teeth; the gaps are in the Test role's individual checks.

**Boundary observations.** The CLI respected a spec rule forbidding `src/` changes during one job (held at boundary, `src/` untouched, probe code went to a test file). It self-corrected an AGENTS.md violation mid-session (removed emoji). A `git show` run *inside* the agent session returned an agent summary, not raw Git output — later confirmed that the chat window is not a verification surface.

**Known error taxonomy (KEDB, finalised).** (1) model attaches explanatory prose to constrained enum fields; (2) model invents enum values; (3) blended citations; (4) accurate citation with useless summary; (5) right entity, wrong attribution; precise-fabricated-figure signature; loose analogy presented as relevance.

**Known open gaps.** Test-role circularity (green runs currently validate placeholder artifacts — the pipeline can pass while the Code role emits non-functional code). Evidence-pack retrieval fragility (GitHub rate limits). A fake-search test gap (nothing asserts the search queries have the right shape).

## Questions to answer

1. Given the evidence above, what is the **single biggest weakness** of this design as it stands? Rank your top three.
2. The v2 spec will define the next build phase. What should it **prioritise**, and in what order? Justify against the evidence, not general best practice.
3. Which of the v1 design's locked decisions (§3–§11 of the design doc) are **most challenged** by this evidence, if any?
4. For the Test-role circularity gap specifically: what validation approach would you use so that a passing pipeline means something real, *without* making the human a bottleneck for every change?
5. What evidence would convince you the system is trustworthy enough to reduce human oversight? Be specific and measurable.
6. What is the most likely way this system **fails badly** in its next three months, and what cheap probe would detect it early?

## Output format

Structured Markdown: numbered answers, each with a one-line verdict, then reasoning tied to specific evidence above. Where you assert a failure mechanism, state which run or observation supports it. If you find yourself reasoning without evidence, label that section **[judgement — unsupported]**.

## Constraints

- Do not modify any files.
- Do not propose changes to the locked decisions without naming the evidence that challenges them.
- No code required — this is a design review.