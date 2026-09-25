---
title: Learning-System Design - Steelman, Standards Cross-check and Advisory Board Review (Part B)
tags: [agent-validation-harness, design, phase-1, review, report]
date: 2026-09-24
status: Phase 1 review draft - recommendations not yet accepted
---

# Part B - Steelman, standards cross-check and Advisory Board review

Companion file: `01-design-process-and-end-to-end-design.md` (Part A).

## 0. How to read this

- **Nothing here is agreed yet.** These are recommendations for you to accept, change or reject, using the same Lever Method as before.
- **Severity tags:** **[MUST]** before build starts, **[SHOULD]** early in the build, **[CONSIDER]** worth deciding, lower urgency.
- **The Advisory Board lenses are my reading of each person's published principles, applied to your design.** They are not statements made by those people, and they carry my own interpretation.
- **Standards were checked against current published sources** (list in section 9). Several are secondary summaries; go to the primary source before you rely on exact wording. Standards were used as review lenses for a new kind of system, so some parts fit loosely.

## 1. Steelman: the strongest case against this design

A design that has only met friendly questions has not been tested. Here is the best case a sceptic would make.

1. **It may cost more than it protects.** Eight stations, a judge, a historian, a sandbox, a second model and an ontology is a lot of machinery for one person with variable capacity. If maintaining it takes more effort than the lessons are worth, the design fails on its own terms.
2. **Independence is claimed, not shown.** Every check is still a model or a person judging model output. Different lineages reduce shared blind spots but cannot prove they are gone. More layers can produce false confidence, which is worse than an honest lack of confidence.
3. **It guards against learning the wrong thing, but a larger risk may be learning too little.** Heavy-by-default, vetoes and expiry all push toward rejection. The design measures wrongly accepted lessons but has no measure of wrongly rejected ones.
4. **A simple alternative may win.** A hand-curated notebook of lessons in Obsidian plus a fixed set of regression tasks might deliver most of the benefit for a fraction of the cost. The design has not been compared against it.
5. **It is entirely untested.** No number in it is measured. Coupling between stations (for example, the ontology, capsules and replay all depending on each other) may create failure modes nobody has seen yet.

**What the steelman changes.** Some parts are cheap insurance and should exist from day one: the immutable ledger, capsules, source stamps, deprecation instead of deletion, and rollback records. Others are expensive machinery that should be earned by evidence: the sandbox, second-model test design, the historian, mutation testing and the hypothesis lane. The build order in section 7 is built on that split, and it includes a baseline comparison and stop conditions so that the design can be simplified if it does not pay for itself.

## 2. Standards cross-check by role

Verdicts: **Met**, **Partly**, **Gap**.

### 2.1 Change management (ITIL 4 change enablement)

ITIL 4 distinguishes three kinds of change: standard (low risk, pre-authorised, well understood), normal (needs assessment and authorisation, with the approver depending on risk), and emergency (expedited, sometimes approved after the fact). It also replaced the old idea that every change goes to one board with a change authority that can be a delegated team, peer review, an automated approval, or business stakeholders for high-risk changes. Its list of warning signs includes unauthorised changes, high rollback frequency and a high share of emergency changes.

| ITIL practice | Our design | Verdict | Change |
|---|---|---|---|
| Standard / normal / emergency change types | Light path and heavy path; nothing for urgent cases | Partly | Add an emergency lane (R7) |
| Standard changes are approved once, then reviewed when modified or after an incident | Light path opens when audits show low misfile rate | Met | Also re-close the light path automatically after a serious miss |
| Change authority matched to risk | Automatic gate for light; reviewer or you for heavy | Met | Write it down as a one-page authority table (R18) |
| Risk assessment and back-out plan per change | Tier rules, frozen rollback triggers, deploy record | Met | None |
| Change schedule and collision control | One lesson per area at a time | Met | None |
| Post-implementation review | Historian, sampled audits | Met | None |
| Health indicators for the change process itself | Not defined | Gap | Track: rollback rate, emergency-lane share, and count of lessons present without a gate record (should be zero) (R8) |

### 2.2 Continual improvement (ITIL 4 continual improvement model)

The model has seven steps: vision, where are we now, where do we want to be, how do we get there, take action, did we get there, and how do we keep momentum. A 2026 post from the ITIL certification body refers to newer ITIL guidance that keeps the seven-step model, so it appears stable across versions.

| Step | Our design | Verdict | Change |
|---|---|---|---|
| Vision, baseline, target | The problem is defined, but there is no measurable target or baseline for the whole system | **Gap** | Define a north-star outcome and baseline before build (R5) |
| Take action | Eight stations | Met | None |
| Did we get there | Historian measures lesson outcomes, not whether the whole system beats a no-learning baseline | **Gap** | Fixed benchmark exam, kept separate from lesson tests (R5, R6) |
| Keep momentum | Retro phase in your working agreement | Partly | Set a review cadence and a standing improvement register; the Ideas Shelf and hypothesis graveyard already work as one |

### 2.3 Agile / Scrum project management

The 2020 Scrum Guide ties quality to a Definition of Done, says work that does not meet it cannot be released, and treats the retrospective as the formal moment to inspect and adapt, including the Definition of Done. Practitioner guidance on limiting work in progress says to adjust limits at reviews, not ad hoc mid-cycle.

| Practice | Our design | Verdict | Change |
|---|---|---|---|
| Definition of Done per item | Gate and vetoes for lessons; none for the build itself | Gap | One Definition of Done per station, agreed before build (R5) |
| Thin vertical slices, working increments | Not yet defined | Gap | Walking-skeleton build order (section 7, R6) |
| Work-in-progress limits | One lesson per area live; exploration budget | Partly | Also cap hypotheses in flight and the human review queue (R11) |
| Inspect and adapt on a cadence | Retro when things break | Partly | Add a scheduled review of thresholds and Definitions of Done |
| Sustainable pace and single-person risk | Your capacity is acknowledged, but you are steward, reviewer and auditor | Partly | Fail-safe defaults when you are unavailable (R11) |

### 2.4 Reliability engineering (SRE)

Google's SRE guidance describes an error budget as an agreed allowance for failure, with a freeze on new releases as the usual last-resort response when it is overspent. It warns that freezing reflexively is not always right, and describes a costly, limited override that itself triggers a postmortem. Its example policy requires a postmortem with a top-priority action item when one incident consumes a large share of budget. Canary releases and blameless postmortems are core practices.

| Practice | Our design | Verdict | Change |
|---|---|---|---|
| Canary and staged rollout | Shadow, canary against control, staged widening | Met | None |
| Automatic rollback | Frozen triggers, red lines and relative drift | Met | None |
| Blameless postmortem | Retro; failures become permanent test cases | Met | Make it a rule for every rollback |
| **Error budget with an agreed freeze policy** | Not defined | **Gap** | A budget for the learning system as a whole: too many rollbacks or regressions freezes new promotions until reviewed, with a rare, costly override (R8) |

### 2.5 Testing practice

| Practice | Our design | Verdict | Change |
|---|---|---|---|
| Test pyramid (many cheap checks, few costly ones) | Mechanical, then judge, then you | Met | None |
| Regression suite from fixed defects | Pinned failures | Met | None |
| Risk-based testing | Blast-radius tiers | Met | None |
| Flaky-test handling | Repeat-and-quarantine | Met | None |
| Test-suite quality (mutation testing) | Planned second | Partly | Keep it second, but start collecting planted-flaw cases now |
| Testing the judge for known biases | Overlap test, calibration | Partly | Add bias probes (R3) |

### 2.6 Judge reliability (LLM-as-judge practice)

Published work and practitioner guides describe recurring judge biases: preference for a particular answer position, for longer answers, and for output from the judge's own model family. Judges can also be manipulated by text inside the answer that tells them to rate it highly, and their scores can shift when the judge model is updated even though the rubric has not changed. Commonly recommended controls are swapping answer order and counting only stable verdicts, controlling for length, using judges from different families, pinning the judge version, and calibrating against human labels on a sample. Reported effect sizes vary by model and task, so treat any number as a range to measure yourself.

| Practice | Our design | Verdict | Change |
|---|---|---|---|
| Different family for judge | Yes | Met | None |
| Pinned, versioned judge and rubric | Yes | Met | None |
| Drift detection after judge changes | Historian, on change | Met | None |
| Order swap and length control | Not defined | Gap | Add as standing probes (R3) |
| Resistance to instructions hidden in the output being judged | Not defined | **Gap** | Judge treats the output as data; test with planted "rate this highly" text (R3) |
| Periodic human calibration sample | Human sees persistent disagreements only | Partly | Add a small fixed-cadence sample (R16) |

### 2.7 Security (OWASP LLM Top 10 2025 and NIST AI RMF)

The 2025 OWASP list covers, among others: prompt injection (including indirect, where instructions hide in content the model reads), sensitive information disclosure, supply chain, data and model poisoning, excessive agency, misinformation and unbounded consumption. NIST's AI Risk Management Framework has four functions (Govern, Map, Measure, Manage), with Govern cutting across the other three; it is voluntary and one source notes it is under revision.

| Threat | Where it lands in our design | Verdict | Change |
|---|---|---|---|
| Indirect prompt injection | Episodes record content the agent read; that content can carry instructions that become lessons | **Gap** | Trust labels on episode content; lessons may not be derived from instructions found inside untrusted content (R1) |
| Poisoning of anything that shapes future behaviour | The lesson store is exactly that | Partly | Single write path, tamper-evident ledger, revocation by provenance (R2, R4) |
| Excessive agency | Roles are separated in principle | Partly | Least privilege per role with separate credentials (R2) |
| Sensitive information disclosure | Cloud-versus-local is on the shelf | Gap | Locality matrix by stage (R14) |
| Unbounded consumption | Budgets enforced from outside, in time | Partly | Hard cost caps on every metered call, enforced outside the agent (R15) |
| Supply chain | Weights provenance flagged in earlier discussion | Partly | Register of models and versions, with source and integrity check |
| Misinformation | Lessons are confident claims | Met | Falsifiers, gate and expiry already address this |

NIST AI RMF as a checklist: **Map** (context, risks) is covered by the capsule, ontology and competency questions; **Measure** by the tests, judge calibration and historian; **Manage** by deployment, rollback and maintenance; **Govern** is thin, because roles, policy and thresholds are scattered across conversations rather than written down (R18).

### 2.8 Ontology engineering (OBO Foundry principles)

The OBO Foundry principles ask for a clearly stated scope, textual definitions, documented and released versions, stable term meaning, and obsolete terms that are marked as deprecated, with guidance on their replacement and advance notice, plus stable identifiers and a named locus of authority.

| Principle | Our ruleset | Verdict | Change |
|---|---|---|---|
| Scope and competency questions | Rule 1 | Met | None |
| Textual definitions | Rule 2 | Met | None |
| Versioning and release | Rule 5 | Met | None |
| Deprecate, do not delete; point to replacement | Rule 4 | Met | Add a pre-announcement step that triggers replay |
| Stable identifiers separate from labels | Not stated | Gap | Give each term a stable ID so relabelling never breaks a capsule (R13) |
| Named authority | Rule 7 (you as steward) | Met | None |

### 2.9 Data governance and records

This area was reviewed from general practice rather than fresh sources. An immutable ledger and a permanent-failure rule pull against any need to delete data. If episodes ever hold personal data about other people (UK data protection law may then apply; this is not legal advice), you need a retention schedule and a way to separate or remove sensitive fields without breaking the ledger (R17).

## 3. Advisory Board review

### 3.1 Tufte lens - can a human actually see what is going on?

**Would challenge:** Review capacity is your scarcest resource, yet nothing defines what you look at. Monitoring that shows one composite score hides the evidence; a rate with no denominator is unreadable.

**Would change:**
- Define a **lesson card**: one page showing claim, citations, scope, falsifier, capsule, source stamps, standing, expiry. Same layout every time.
- Historian output as **small side-by-side charts of raw counts** (verdicts by judge version over time), not a health index. Every rate shows its sample size.
- Every summary links to the raw ledger entries beneath it.
- Show near-misses and disagreements next to each other, since disagreement is the system's most informative event.

**Why it fits better:** you audit only the exceptions, so exceptions must be quick to read and hard to misread. (R12)

### 3.2 Feynman lens - are we fooling ourselves?

**Would challenge:** The design contains many mechanisms and no evidence any of them works. Rituals without evidence are cargo-cult process. The easiest people to fool are the designer and the dashboards.

**Would change:**
- **Set thresholds and stop conditions before seeing data**, and write them down (R10).
- **Measure the gate's accuracy in both directions.** Accepted lessons that fail live show wrongly accepted. Sampled shadow runs of rejected lessons show wrongly rejected (R9).
- Give every mechanism a "what would show this doesn't work" test, so each one can be removed if it fails.
- Report failures and doubts alongside successes in every review pack.
- Run one **end-to-end planted-flaw test**: plant one genuinely good unusual lesson and one that only looks good; the system passes if it keeps the first and kills the second.

**Why it fits better:** the design's central problem is self-deception, so it must be tested against self-deception, not just built to resist it.

### 3.3 Karpathy lens - does it beat the simple baseline?

**Would challenge:** Complexity arrives before any baseline exists. No one knows whether a naive approach (appending notes to context) already gets most of the gain.

**Would change:**
- **Build the exam first.** A fixed benchmark of real tasks, run with no learning loop, with naive notes, then with the system (R5, R6).
- **Skeleton first, with dumb components.** Get a trivial end-to-end loop running and trusted, then add one mechanism at a time, checking each one helps.
- **Read real episodes by hand before automating capture.** You cannot design what an episode should contain until you have seen forty of them.
- Keep the judge's rubric small and versioned. Rubric sprawl is how judges become unreliable.
- Verify each station on a toy task with a planted lesson before real data.

**Why it fits better:** it turns the design from a specification into a sequence of cheap experiments, each of which can fail early.

### 3.4 Security expert lens - what breaks it on purpose?

**Would challenge:** The lesson store is the highest-value target: whatever writes a lesson steers every later decision. The design records what the agent read, and that is exactly how injected instructions get in. The judge reads output that may address it directly.

**Would change:**
- **Trust labels** on episode content (from you, from a trusted tool, from untrusted content). Lessons may not be derived from instructions embedded in untrusted content (R1).
- **One write path.** Only the gate writes standing lessons. Separate credentials for capture, learner, judge, gate and deploy. Append-only ledger with tamper evidence (R2).
- **Revocation by provenance.** Because lessons cite their episodes, one suspect episode lets you quarantine everything built on it (R4).
- **Judge hardening:** treat output as data, and test with injected instructions (R3).
- **Locality matrix:** for each stage, whether an external model may be used and what data may leave (R14).
- **Hard cost caps** enforced outside the agent (R15).
- Register of model weights and versions with source and integrity checks.

**Why it fits better:** the design already assumes the lesson store is an attack surface; these turn that assumption into controls.

## 4. Consolidated recommendations

| ID | Sev | Station | Change | Lens | Cost |
|---|---|---|---|---|---|
| R1 | MUST | 1, 2 | Trust labels on episode content; no lessons from instructions in untrusted content | Security | Low |
| R2 | MUST | 1, 6 | Single write path through the gate; per-role credentials; append-only tamper-evident ledger | Security, OWASP | Low to medium |
| R3 | MUST | 5, 6 | Judge bias and injection probes: order swap, length control, cross-family, planted "rate this highly" text | Judge practice, Security | Medium |
| R4 | MUST | 8 | Revocation by provenance using the citation links | Security | Low |
| R5 | MUST | All | North-star outcome, baseline benchmark, and a Definition of Done per station | ITIL CI, Scrum, Karpathy | Medium |
| R6 | MUST | Build | Walking-skeleton build order and baseline comparison (section 7) | Karpathy, Agile | Low |
| R7 | SHOULD | 7 | Emergency lane for urgent harm, with review after the fact; default action is rollback | ITIL | Low |
| R8 | SHOULD | 7, 8 | Error budget and promotion freeze for the whole system; track rollback rate and unrecorded lessons | SRE, ITIL | Low |
| R9 | SHOULD | 6 | Sample-shadow a small share of rejected lessons; gate accuracy report in both directions | Feynman | Medium |
| R10 | SHOULD | All | Pre-registered thresholds and stop conditions for every mechanism | Feynman | Low |
| R11 | SHOULD | 6, 7 | Fail-safe defaults when you are unavailable: unreviewed means not promoted; provisional lessons expire; cap the review queue | Scrum, your capacity | Low |
| R12 | SHOULD | 6 | Lesson card standard; denominators on every rate; raw counts over composite scores | Tufte | Low |
| R13 | SHOULD | 3 | Stable term identifiers separate from labels | OBO | Low |
| R14 | SHOULD | All | Locality matrix: which stages may use external models and what data may leave | OWASP, air-gap | Low |
| R15 | SHOULD | 2, 5 | Hard cost caps on metered calls, enforced outside the agent | OWASP | Low |
| R16 | CONSIDER | 6 | Fixed-cadence human calibration sample; judge rotation for the highest tier | Judge practice | Medium |
| R17 | CONSIDER | 1, 8 | Retention schedule and separable sensitive fields | Data governance | Low |
| R18 | CONSIDER | All | One-page governance policy: roles, authority table, thresholds | NIST AI RMF | Low |
| R19 | CONSIDER | All | Independent review of this design by a different model and by you (see section 8) | Feynman | Low |

## 5. What changes in the design

- **Additions:** trust labels; single write path and tamper evidence; judge bias and injection probes; revocation by provenance; emergency lane; system error budget; false-rejection sampling; pre-registered thresholds; lesson card; term identifiers; locality matrix; cost caps; governance page.
- **Modifications:** Station 1 records content trust; Station 5 and 6 gain judge probes; Station 6 adds gate-accuracy reporting; Station 7 adds emergency lane and freeze rule; Station 8 adds revocation.
- **Sequencing change:** the build follows a walking skeleton and earns each next piece by evidence (section 7). No station is removed.

## 6. Where the review and your instincts agree

- Your instinct for heavy-by-default, hard vetoes and a judge with calibration underneath matches change-management and SRE practice.
- The historian with no vote matches the separation-of-duties idea in change and audit practice.
- Deprecate-never-delete matches ontology practice and blameless learning from failure.

## 7. Proposed build order for Phase 2 (for discussion)

Each slice must show measured benefit or reduced risk over the last, or it is simplified or dropped.

| Slice | Contents | Exit test |
|---|---|---|
| 0 Paper run | Record 10 to 20 real episodes by hand in Obsidian; write 3 to 5 lesson cards; you act as the gate; run the baseline benchmark with no learning and with naive notes | You can make a gate decision quickly from a card; the baseline numbers exist |
| 1 Ledger | Append-only ledger, mechanical index, source stamps, trust labels (R1, R2) | Episodes findable; nothing editable after the fact |
| 2 Capsule | Fixed capsule fields, 10-term ontology with stable IDs, replay of pinned failures | A lesson's capsule matches or rejects a new situation sensibly |
| 3 Judge | Judge with calibration set, bias and injection probes, repeat-and-quarantine (R3) | Judge agrees with mechanical checks; probes are caught |
| 4 Deploy | Shadow, rollback record, red-line triggers, error budget (R8) | A bad lesson is rolled back mechanically |
| 5 Tiering and sandbox | Tier routing, sandbox, different-lineage test designer, held-out protections | Planted-flaw end-to-end test passes |
| 6 Maintain | Decay, sentinels, pins, compaction, historian | Old lessons retire correctly under a changed environment |
| 7 Extras | Mutation testing, hypothesis lane waterfall | Only if slices 0 to 6 beat the baseline |

**Stop condition to write down now:** if the system has not beaten the naive-notes baseline on the fixed benchmark by an agreed margin after an agreed number of episodes, stop adding machinery and simplify. Set the margin and count before you see any data.

## 8. Limits of this review

- **Same-family blind spots.** This review was produced by the same model that helped design the system. It is exactly the situation the design warns about. An independent review by a different model, and by you, is recommended (R19).
- **Sources.** Several sources are secondary or practitioner summaries. A 2026 source refers to newer ITIL guidance (called Version 5); the review used ITIL 4 terms, which that source suggests are carried forward, but check the edition you rely on. NIST's framework was described by one source as under revision.
- **Not covered:** the comparison against the Hermes baseline set in your working agreement, exact thresholds, and any legal review of data handling.
- **Lenses are interpretations.** The four Advisory Board perspectives apply publicly known principles; they are not endorsements or statements.

## 9. Sources consulted

ITIL and change enablement
- https://itsm.tools/?p=34945
- https://dev.blogs.bmc.com/itil-change-enablement/
- https://www.givainc.com/itil/change-enablement
- https://www.splunk.com/en_us/blog/learn/change-management.html

ITIL continual improvement
- https://dev.blogs.bmc.com/itil-continual-improvement/
- https://clearbridgetech.com/itil/itil-continual-improvement
- https://community.peoplecert.org/public/clubs/itil/blogs/continual-improvement-maturity-or-transformation-2026-02-04

Scrum and agile
- https://scrumguides.org/docs/scrumguide/v2020/2020-Scrum-Guide-US.pdf
- https://www.scrum.org/node/16616

Site reliability engineering
- https://cloud.google.com/blog/products/devops-sre/good-housekeeping-error-budgetscre-life-lessons
- https://sre.google/workbook/error-budget-policy

Security
- https://www.bdemerson.com/article/owasp-llm-top-10
- https://aembit.io/blog/owasp-top-10-llm-risks-explained/
- https://nordlayer.com/learn/ai-security/nist-ai-risk-management-framework/
- https://www.morganlewis.com/pubs/2023/02/nist-releases-new-ai-risk-management-framework
- Primary: OWASP Gen AI Security Project and NIST AI RMF (go to the publishers for exact wording)

LLM-as-judge
- https://arxiv.org/pdf/2410.21819
- https://memx.app/glossary/llm-as-a-judge/
- https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/

Ontology engineering
- https://obofoundry.org/principles/fp-000-summary.html
- https://obofoundry.org/principles/fp-004-versioning.html
- https://obofoundry.org/principles/fp-019-term-stability.html
