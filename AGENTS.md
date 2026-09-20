# AGENTS.md — self-improving-agents

> Project rules for any AI agent (Vibe CLI, VS Code extension, web sessions) working in this repo. Read this file fully before making any change. It is the single source of truth for conventions; if chat instructions and this file conflict, **this file wins** — and say so out loud when it happens.

## What this project is

A self-improving agent system: agents hold memory and context over time, log changes to a change board, and manage improvements through defined roles (Review, Plan, Code, Test, Sign off). Governance is the product — the trace log and change board are not logging sugar, they are the point.

- Repo: `github.com/BrixDez/self-improving-agents` (currently public as a workaround; contains no secrets — keep it that way)
- Local path: `C:\Mistral\self-improving-agents` (Windows — Python, stdlib-first)
- Core modules: `src/backbone.py` (SQLite, hash-chained append-only trace log, change board, goal-drift guard, test-run counter), `src/agent.py` (Review role), `src/search_grounding.py`, tests in `tests/`

## Hard rules — never break these

1. **The API key lives only in the `MISTRAL_API_KEY` environment variable.** Never write it to code, files, chat, logs, trace payloads, or screenshots. If it appears anywhere, stop and tell Paul immediately.
2. **The trace log is append-only.** Never UPDATE or DELETE from `trace_log`. The hash chain must verify (`trace chain: OK`) after any change you make.
3. **The locked job spec is immutable.** Never edit a locked spec; it is re-injected verbatim at every role handoff by design.
4. **All state changes flow through the change board.** No direct edits to board tables, and Tier 2 changes (invariants, trace config, rollback machinery, tier rules) always need Paul's human sign-off.
5. **`Test` never edits what it tests; `Sign off` never grades its own work.**
6. **Log test-run counts per change.** Do not re-run a test until it flakily passes — that is a criteria change in disguise and must go through the board.
7. **No secrets in commits.** `.gitignore` already excludes `.env`, `*.key`, `*.db`. Verify with `git status` before any commit.

## Conventions

- Python, standard library first (`sqlite3`, `urllib`/`http` for HTTP). Justify any new third-party dependency before adding it.
- Deterministic mock mode when `MISTRAL_API_KEY` is unset — every feature must stay testable without live calls.
- **Constrain at the parser boundary, not the prompt** (KEDB v1.1/v1.2 lesson): normalise synonyms, reject/conservatively fall back on unknown enum values, require a `url` field for recommendations, preserve the model's original wording as `model_type`.
- **Fail closed on empty evidence.** A run with no evidence pack is a failed run, not a best-effort run.
- Tests: two kinds — deterministic pass/fail scripts, and invariant checks over trajectories (history append-only, role boundaries, all changes via board). New failure modes discovered in runs become KEDB entries.
- Windows host: use `python -c` one-liners or scripts for board/report queries; paths use backslashes locally.

## Working method with Paul

- **Build first, explain in the cracks.** One finished thing per session beats a pile of half-understood pieces.
- Before any non-trivial implementation, ask Paul to **predict what will happen** — once, then move on. Never quiz-gate progress.
- **Origin-track**: when summarising work, distinguish Paul's decisions/ideas from AI-implemented work.
- **Design walkthroughs are part of review**, not a one-off — Paul validates and learns by questioning the design in the loop.
- Be honest about status: interesting idea ≠ plausible design ≠ working prototype ≠ demonstrated product. Never blur these lines.
- If a subtle trap appears (agent failure mode, fragile assumption), flag it briefly and let Paul decide whether to dig in.

## Git loop (Paul is a git novice — keep it simple)

```
edit → git add -A → git commit -m "..." → git push
```

Suggest one commit per meaningful change with a plain-English message. Explain any command that isn't part of this loop before running it. Never force-push. If a merge editor opens, stop and walk Paul through it.

## Known failure modes (KEDB — add to this list, never silently "fix around" one)

1. Model attaches explanatory prose to constrained enum fields
2. Model invents enum values (e.g. "source_expert")
3. Blended citation (real source + fabricated specifics)
4. Accurate citation / useless summary
5. Right entity, wrong attribution
6. Precise-fabricated-figure signature
7. Loose analogy presented as relevance

## Status

Durable project status, decisions, and run history live in the Vibe Knowledge topic `project-state` — not in this file. This file covers conventions only; do not let it drift into a status log.

---

*When this file and reality diverge, update this file — via a normal commit — and tell Paul what changed and why.*