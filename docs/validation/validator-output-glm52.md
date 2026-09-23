I read both files earlier this session. I have them in context — no files have changed since. Let me answer the six questions in full now.

Validator Output — v1 Design Review
1. Single biggest weakness + top three ranked
Verdict: The biggest weakness is that the pipeline can pass end-to-end while emitting artifacts that are not real — placeholder code, fabricated claims behind real URLs, and empty payloads all passed the Test role.
Ranked top three:
 1.  Test-role circularity. Green runs validate placeholder artifacts. The Code role emits deterministic placeholder code with no LLM, changes are not applied to the filesystem, and the Test role passes anyway. A passing pipeline therefore does not prove that working code was produced or that recommendations are substantively correct. (Evidence: "known open gaps" explicitly names this; Run 2 caveat that grounded URLs ≠ grounded claims.)
 2.  Claim-level validation gap. Run 2 achieved 10/10 verifiable URLs, but the prose describing those sources was never checked against source content. Run 1 showed 9/10 recommendations carried fabricated or embellished specifics. URL membership enforcement catches fake sources but not misrepresentation of real ones — which is KEDB items 3 (blended citation), 5 (wrong attribution), and 6 (fabricated figures).
 3.  Evidence-pack retrieval fragility. GitHub rate limits can silently degrade or empty the evidence pack. The fail-closed rule mitigates this, but nothing asserts the search queries themselves have the right shape (the "fake-search test gap"). A malformed query that returns irrelevant results would pass the URL-membership check while producing useless recommendations.

2. v2 priorities and ordering
Verdict:
 1.  Make the Test role validate executed artifacts, not placeholders. Until a passing pipeline means the Code role's output was actually run, every "green" result is ambiguous. This is the root cause that makes all other validation results untrustworthy.
 2.  Add claim-URL reconciliation. For each recommendation, fetch the cited URL and verify the claimed evidence (quotes, figures, attributions) appears in the source. This directly closes the Run 2 caveat and targets KEDB items 3, 5, 6 — the failure modes that survived grounding.
 3.  Harden evidence retrieval and add query-shape assertions. Rate-limit backoff, retry logic, and a test that asserts the harness emits queries derived from the locked spec with the expected structure. This prevents silent degradation of the evidence pack.
Justification against evidence (not general best practice): Priority 1 is driven by the explicit open gap that green runs validate placeholders. Priority 2 is driven by Run 2's caveat and Run 1's 9/10 fabrication rate. Priority 3 is driven by the two named open gaps (rate limits, fake-search test gap). No priority is justified by abstract concern; each traces to a named observation.

3. Locked decisions most challenged by evidence
Verdict: §5 (Validator) and §6 (Test Design) are most challenged. §10 (Security Stack) is partially challenged.
§5 (Validator — hybrid planted-flaw + KEDB approach). The planted-flaw probe (Run 3) was designed to give a baseline catch rate. It detected secret leaks but failed to detect fabricated evidence URLs and empty payloads. The hybrid approach is sound in principle, but the evidence shows the current planted-flaw set does not cover the failure modes that actually matter — the ones that slipped through. The KEDB is finalised but not yet wired into automated checks. The design's assumption that planted flaws give a meaningful baseline catch rate is challenged: the baseline is 1/3 flaw types detected.
§6 (Test Design — invariants over trajectories). The structural invariants held (trace chain OK, role boundaries respected, board-mediated changes). But the design assumes that passing tests means something real. The Test-role circularity gap means the trajectory invariants pass while the substance is unvalidated. The design's framing of "expected behaviour: scripted, deterministic, pass/fail" is correct for invariants but insufficient for artifact quality — and the evidence proves it.
§10 (Security Stack — post-execution output validation). Secret leaks were detected (Run 3), which validates item 3 (PII/leak checks). But fabricated URLs and empty payloads were not detected, which means the post-execution output validation layer has a real gap. The design lists it as covered; the evidence says it is not.
Not challenged: §3 (trace log — held perfectly), §4 (change board — boundary principle held, Run 3 aborted correctly), §7 (conflict-of-interest probe — circularity check held), §11 (replay simulator — not yet exercised, no evidence).

4. Test-role circularity: validation approach without human bottleneck
Verdict: Separate artifact execution from artifact evaluation, and automate both.
Approach:
For Code-role outputs:
•  Require the Code role to produce artifacts that are executable in a sandbox. After Code emits, the pipeline automatically applies the change to a sandboxed copy of the repo, runs the existing deterministic test suite, and fails if any test fails or if the artifact does not compile/import.
•  This eliminates the placeholder problem by definition: a placeholder that does not implement the change fails the smoke suite.
•  The human is not involved unless the sandbox run fails in a way the Test role cannot diagnose.
For Review-role recommendations:
•  Run an automated claim-URL reconciler before the Test role accepts the batch. For each recommendation, fetch the cited URL, extract the source text, and verify that the specific claims (quoted text, named figures, attributed findings) appear in the source. Empty payloads fail closed (already the rule, but not enforced by the Test role — Run 3 showed it was not detected). Mismatched claims fail.
•  This is deterministic, automated, and requires no human review unless a mismatch is flagged for adjudication.
Why this avoids the human bottleneck: Both checks run inline in the pipeline. The human only sees the change board when automation passes and the recommendation is ready for sign-off, or when automation fails and the dispute goes to Review (per the existing T→R dispute path). The human is a gate for Tier 2 changes only, not for every artifact validation.
Evidence tie: This directly addresses the planted-flaw probe gaps (fabricated URLs and empty payloads undetected) and the Run 2 caveat (grounded URLs ≠ grounded claims).

5. Evidence that would convince me to reduce human oversight
Verdict: I would reduce oversight only after the following metrics are sustained over 100 consecutive real (non-placeholder) runs:
 1.  Planted-flaw detection rate ≥ 95% across all flaw types — not just secret leaks. The current baseline is 1/3 (Run 3). Until fabrication and empty-payload detection are proven, the validator has not demonstrated coverage.
 2.  Claim-URL reconciliation pass rate = 100% — every recommendation's claimed evidence is verified against fetched source content with zero mismatches found in post-hoc audit.
 3.  Human rubric scores: mean ≥ 4.0, no individual score < 3 across all five criteria (Novelty, Relevance, Evidence quality, Actionability, Vision alignment) over the 100-run window. The design (§8) already defines this threshold; I would hold it.
 4.  Test-run counter shows exactly one run per change with zero instances of re-rolling (already an invariant, but needs to be proven over the window, not just asserted).
 5.  Trace chain verifies for every entry with no manual corrections needed (already proven in all three runs; sustained over 100 runs would be convincing).
 6.  Zero KEDB additions from the 100-run window — meaning no new failure mode emerged that the system did not already catch. If new KEDB entries appear, oversight stays.
Why these specific numbers: 100 runs is enough to see recurrence of the observed failure modes (Run 1 fabricated 9/10, Run 3 missed 2/3 flaw types — these rates would surface quickly). The 95% planted-flaw threshold is strict because the current baseline is 33%; reaching 95% proves the gaps were closed, not just partially addressed. Zero KEDB additions is the strongest signal: it means the system is catching what it encounters, not just what it was designed to catch.

6. Most likely bad failure in next three months + cheap probe
Verdict: The most likely bad failure is silent claim fabrication behind real URLs — recommendations that cite genuine, resolvable sources but misrepresent their content (embellished figures, wrong attribution, invented specifics presented as quotes).
Why this is most likely: It is the exact failure pattern already observed (Run 1: 9/10 recommendations had fabricated or embellished specifics; Run 2: URLs verified but claims unchecked). It passes every current automated check (URL membership, fail-closed on empty pack, trace chain, role boundaries). It is the natural failure mode of a system that validates sources but not claims about sources. KEDB items 3, 5, and 6 all describe this family. The system has no current defense against it.
Cheap early probe: A nightly reconciliation script that iterates every recommendation on the change board, fetches each cited URL, and performs string matching (or simple semantic similarity) between the recommendation's evidence text and the fetched source content. Flag any recommendation where the claimed quote, figure, or attribution does not appear in the source. Cost: a few hundred HTTP requests + string comparisons per night. If even one mismatch is found, the system is producing fabrications that pass all current checks — and oversight should not be reduced.
Evidence support: Run 1 (9/10 fabricated specifics), Run 2 caveat ("grounded URLs ≠ grounded claims — the agent's prose describing those sources has not yet been spot-checked"), KEDB items 3/5/6, and the planted-flaw probe gap (fabricated evidence URLs not detected).