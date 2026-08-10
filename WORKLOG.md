# Worklog

One dated line per work session, newest on top: where the code stopped, the single next move, any open confusion. This exists because commits record what finished, not what was mid-thought; the next session reads the top line and starts moving in seconds. Purely technical, about the code's state, nothing else.

Format: `YYYY-MM-DD: stopped at X. Next: Y. Open: Z.`

---

- 2026-08-10: `load_lesson_content` rewritten for a flat folder; `VAULT_COURSES_PATH` renamed `VAULT_PATH` and repointed at `03 Life/Learning/Fields/Decentralized AI/Lessons`. No existence guard added: a missing vault crashes loud, chosen deliberately over a silent empty string. Found that `courses.json` is a cached parse and not a pointer, which is why boot never failed on the dead path. `review` now runs end to end and all six drawn cards return empty content, because the 22 stored cards name a course deleted on 2026-08-05 and no filename can match. Next: card identity per the STRATA engine rework, one card per lesson retrieval prompt, storing source path and heading; archive the old 22 rather than migrate. Open: `cmd_review` line 92 submits `Rating.Again` when a lesson file is missing and `save_review_state` persists it, so a tooling failure is written as a memory failure; the summary then reports "Reviewed: 6" with "Duration: 0.0s". Six cards already carry a false Again from this run.

- 2026-08-09: repo designated the current build artifact; STRATA.md spec and engine rework written; no code touched yet. Next: get the agent running locally (Practice Loop step 1), expect the parser to fail on the retired Courses/ path. Open: whether review_state.json loads at all with courses.json pointing at a dead path, check before touching the parser.
