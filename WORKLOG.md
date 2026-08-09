# Worklog

One dated line per work session, newest on top: where the code stopped, the single next move, any open confusion. This exists because commits record what finished, not what was mid-thought; the next session reads the top line and starts moving in seconds. Purely technical, about the code's state, nothing else.

Format: `YYYY-MM-DD: stopped at X. Next: Y. Open: Z.`

---

- 2026-08-09: repo designated the current build artifact; STRATA.md spec and engine rework written; no code touched yet. Next: get the agent running locally (Practice Loop step 1), expect the parser to fail on the retired Courses/ path. Open: whether review_state.json loads at all with courses.json pointing at a dead path, check before touching the parser.
