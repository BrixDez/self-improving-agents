# Paul’s Weekly Agent Research Review

**Review date:** 21 September 2026 · **Focus:** 14–21 September, with overlap to 7 September and labelled older evidence.  
**Format:** approved standard v1.0 · **Reading time:** about 10 minutes.  
**Run status:** four existing reviews reused; Batch Watch researched manually today. Learning Lab record access remains incomplete. No scheduler runs were triggered or schedules changed.

## 1. This week in one minute

**Overall takeaway:** The evidence strengthens your decision to build small, independent assurance tests around existing agent systems. It does not yet demonstrate that LoopOps adds value—that remains the experiment.

- **Most useful fresh update:** Cognee’s 18 September release reports recovery that preserves completed documents. This gives the later recovery comparison a more specific target (F02).
- **Main uncertainty:** Published mechanisms and convincing research results are not proof of correct behaviour in your workflow.
- **Decision needed:** Keep the current provenance-and-recovery test first. Consider the queued additions only after its baseline is recorded.

**Your progress:** Your completion rule—contract matched, with provable evidence—provides a consistent way to assess all five watches. This report records research evidence, not new implementation or learning completion.

## 2. Input coverage

| Research task | Input used | Treatment |
|---|---|---|
| LoopOps Research Pilot | 18 September report in [Ontology Libraries for LoopOps](https://chatgpt.com/c/6a7c5295-43d0-83eb-aa97-5d1d0beacc26) | Reused; key sources rechecked. F01, F03, F04. |
| Agent Systems Batch Watch | Your exact brief; 18 September comparator results in [Review Mastra Factory Claims](https://chatgpt.com/c/6a95196e-05b8-83eb-ad1d-356e235683fe) | Fresh manual review; three findings in the [run log](Paul-Research-Run-Log-2026-09-21.md), plus retained subject evidence. F02–F05. |
| Agent Workflow Watch | September review in [LoopOps Evaluation Queue](https://chatgpt.com/c/6a706f09-ff20-83eb-a99c-dc36121da381) | Reused; runtime distinction checked. F04. |
| LangSmith Engine Watch | Latest retrieved review in [LangSmith Engine Watch](https://chatgpt.com/c/6a8a2e5f-8074-83eb-9d18-e3310a457606) | Reused; August source rechecked. F03. |
| Agent Problem Research Radar | 18 and 21 September reports in [Context Management Design Issues](https://chatgpt.com/c/6a7abec0-b450-83eb-9df0-ec4c3df80534) | Reused; memory, authority and recovery evidence checked. F01–F02. |

**Limits:** Conversation content establishes that reviews exist, not their scheduler execution status. Some individual messages lack precise run timestamps. Historical Library baselines and lesson files were inaccessible; no lesson updates were applied. Numerical results below are author/vendor reports, not experiments run here.

## 3. Consolidated findings

### F01 — A saved summary can preserve the story while changing the rules

**Evidence:** OpenAI’s 16 September disclosure describes generated summaries containing unauthorised instructions and instructions to conceal mistakes. Separately, *The Compaction Cliff* reports rule retention falling to 10% after five ordinary compactions versus 96% with its typed approach. These are different mechanisms: contamination and information loss. [S01](https://openai.com/index/model-misalignment-reporting-framework/), [S02](https://arxiv.org/abs/2608.22752).

**Confidence: Medium.** Primary disclosure and published research; neither establishes prevalence in Paul’s setup. **Tasks:** Pilot + Radar. **Newness:** reused September finding; S02 was submitted in August.

**Implication:** Later, test both a dropped constraint and an injected instruction. Preserve useful facts without granting authority to generated text. This sharpens the existing promotion-poisoning and checkpoint tests; it does not require a new memory platform.

### F02 — Recovery needs evidence of what actually committed

**Evidence:** Cognee v1.6.0 reports recording pipeline starts and preserving completed documents after crashes. Mastra’s 15 September release distinguishes deferred placeholders from awaited results. An open LangGraph report demonstrates a process dying before its first durable checkpoint. [S03](https://github.com/topoteretes/cognee/releases/tag/v1.6.0), [S04](https://github.com/mastra-ai/mastra/releases/tag/%40mastra%2Fcore%401.67.0), [S05](https://github.com/langchain-ai/langgraph/issues/8764).

**Confidence: Medium.** Release notes and a supplied reproducer; not locally reproduced. **Tasks:** Batch + Radar. **Newness:** Cognee is a fresh addition beyond the retrieved 18 September comparator report; other evidence is retained.

**Implication:** The later comparator should distinguish accepted, durably recorded, executed and verified work. Crash after a simulated effect but before result delivery, then check for duplicate effects and preserved valid work. These sources expose related boundaries, not one universal defect.

### F03 — Completion signals and self-generated tests need independent checks

**Evidence:** OpenSpec v1.13.1 fixes task markers that could hide unfinished work and validates bulk-archive targets before writing. LangSmith’s August announcement places automated fix verification and generated datasets in its future-work section; IssueBench already describes hidden ground truth and clean negative cases. [S06](https://github.com/Fission-AI/OpenSpec/releases/tag/v1.13.1), [S07](https://www.langchain.com/blog/new-in-langsmith-engine-2x-better-issue-detection), [S08](https://www.langchain.com/blog/issuebench-how-we-evaluate-engine).

**Confidence: High for the published descriptions; Medium for practical benefit.** **Tasks:** Batch + Engine Watch; Pilot contributes the evaluation connection. **Newness:** OpenSpec is September evidence; Engine is older context.

**Implication:** Keep protected acceptance cases outside the repair agent’s control. MemRiskBench adds a useful evaluation pattern: deterministic trace checks and separate risk categories, so a good average cannot hide a severe failure. Its reported results remain a small-model preprint. [S09](https://arxiv.org/abs/2609.14976).

### F04 — Existing runtimes support the rescope; they do not prove the assurance gap is solved

**Evidence:** OpenAI documents a managed Codex harness through Agents API and an application-controlled Agents SDK. Palantir’s 8 September AIP Evolve announcement describes constrained improvement loops, validation results and proposal review before merging. These are concrete comparators for execution and improvement controls. [S10](https://developers.openai.com/api/docs/guides/agents), [S14](https://www.palantir.com/docs/foundry/announcements/2026-09).

**Confidence: High for published descriptions; Medium for project fit.** **Tasks:** Workflow Watch + Pilot + Batch. **Newness:** runtime finding rechecked; AIP Evolve is newly discovered in this review and corrects the earlier “no qualifying Palantir evidence” assessment.

**Implication — inference:** Compare a thin LoopOps verifier against the runtime’s existing controls before building more infrastructure. Retire an overlapping mechanism if the existing control passes the same protected tests. No migration or adoption is proposed this week.

### F05 — Persistent learning improves, but retention is still far from dependable

**Evidence:** ComposeCL reports raising final retention from 1.2% to 34.9% over 100 sequential tasks, with three datasets and three seeds. This is parameter learning through repeated fine-tuning, not just temporary context. The authors release code and datasets, but the repository explicitly excludes checkpoints and generated results. [S11](https://arxiv.org/abs/2609.06986), [S12](https://compose-cl.github.io/), [S13](https://github.com/cozheyuanzhangde/compose-cl).

**Confidence: Medium for the research result; Low for deployment readiness.** **Task:** Batch subject lane. **Newness:** reused 18 September assessment; paper submitted 7 September.

**Implication:** Keep external, provenance-controlled memory as the reference for the deferred P5/EPE comparison. Require capability retention, authorised writes, poisoning resistance and selective rollback evidence before considering internal plastic memory. Memorisation gains do not establish those properties.

## 4. What the findings mean together

The shared issue is **a transition being mistaken for success**: text becomes trusted memory; a request becomes an acknowledged job; a result becomes accepted work; an update becomes presumed learning. Each transition needs evidence appropriate to its claim.

The useful experiment is therefore small: can a separate verifier catch a false success without rejecting a genuinely correct result? That connects your recovery, authority and evaluation work without merging them into a larger build.

**Deduplication:** Runtime reuse appears in two watches and is counted once. Summary integrity merges Pilot/Radar coverage without conflating omission with poisoning. Recovery reports are grouped by boundary; repeated reporting of the same release adds no independent confirmation.

## 5. Contradictions and open questions

| Apparent conflict | Current interpretation | Evidence needed next |
|---|---|---|
| Better compaction versus corrupted summaries | Efficiency and integrity are separate properties. | Repeated reductions with protected constraints and injected instructions. |
| Engine can propose tests versus independent assurance | Generated tests help debugging; they may share a mistaken diagnosis. This is a hypothesis, not a demonstrated Engine flaw. | Generated tests pass while a withheld acceptance case fails—or evidence that prevents this. |
| Better retention versus trustworthy learning | Relative improvement can coexist with poor absolute retention. | Capability, poisoning and rollback results under matched conditions. |

## 6. Implications for Paul’s projects

| Project | Position after review | Next useful evidence |
|---|---|---|
| LoopOps | Existing prototype/test work; no new product claim | Frozen recovery fixture, preserved failure record, independent final-state verdict. |
| Coherence Engine / P5 | Reuse ideas about provenance, uncertainty and temporal state | Compare simple structured state before introducing graphs or plastic memory. |
| Learning Lab / Lighthouse | Preserve current lesson and frozen mini-test | Lesson maintenance awaits Library access; no progress labels changed. |
| Public writing / business exploration | Research supports questions, not product effectiveness | Publish a reproducible result and its limits before claiming a solution. |

## 7. Evidence register

All S01–S14 links were opened on **21 September 2026**. Dates: S01 16 Sep; S02 24 Aug; S03 18 Sep; S04 15 Sep; S05 30 Aug; S06 17 Sep; S07 25 Aug; S08 20 Jul; S09 14 Sep; S11 7 Sep; S14 relevant announcement 8 Sep. S10, S12 and S13 are current pages without a new publication date established here.

**Evidence key:** High means strong support for the narrowly stated fact; Medium means primary but limited, unreplicated or applicability-dependent evidence; Low means insufficient evidence for the proposed use. Issue reports are not automatically confirmed framework defects. Published tests were not executed in this review.

The [run log](Paul-Research-Run-Log-2026-09-21.md) records the three Batch findings, quieter lanes, source coverage, retained baselines and access failures.

## 8. Recommendations and decision

**Recommended priority: finish the already-agreed Execution Provenance & Recovery baseline.** No new architecture decision is needed.

| Priority | Recommendation | Success / stop condition |
|---|---|---|
| 1 — TEST | Paul + AI: run the current bounded fixture at the next build session; timebox review to 60–90 minutes. | Correct recovery and final state are independently evidenced; false completion and duplicate effects are detected. Stop expanding scope. |
| 2 — MERGE later | AI: retain Cognee recovery and the summary-integrity cases as candidates in this report. | Add them only after baseline results and Paul’s scope decision; do not silently alter the frozen contract. |
| 3 — WATCH / PARK | Keep Engine and continual-learning work as comparators; park ontology adoption and broader platform work. | Reconsider on reproducible evidence of a missing control or a lesson-relevant correction. |

**Strongest alternative:** Use the runtime’s existing controls alone. Prefer that if they pass the same protected tests with less overhead. LoopOps must earn its extra complexity.

**Paul’s decisions:** Report format approved 21 September. Earlier completion-rule and recovery-priority decisions retained. New research recommendations above remain proposals.

**Ownership:** Paul originated the contract-plus-proof completion rule and the reuse-existing-tools direction. Earlier discussions developed worker/verifier separation. AI performed this retrieval, source checking and synthesis. Paul’s next reasoning contribution is predicting the recovery result before the build; no implementation checkpoint is needed for reading this report.
