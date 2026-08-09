# Strata

A local visual face for the Smart Repetition Agent: a stratigraphic column of a learning field, served at localhost, two-way. Named for the same reason the podcast is: layers, read from the bottom.

Decided 2026-08-08. This document is the spec the build hours implement, phase by phase. It lives in the repo so the repo carries its own intent.

## What it is

One page, served locally by this codebase (FastAPI), opened by hand when wanted. It reads three stores that already exist and renders them as one picture:

- **The vault** (path in config): the field syllabus (`Decentralized AI From the Beginning - Syllabus.md`), its stages, position line, visited lists with curation marks, Missing lists; lessons and their `## Retrieval prompts` sections; digest stratum tags; narration files; Main Notes.
- **FSRS state** (`data/review_state.json`): which cards are due, per stage. A due card is a fact about a concept's decay curve.
- **Git** (configured repo paths): what each repo gained, as repo facts.

## The column

The main view is a stratigraphic column: ten layers, Stage 0 at the bottom, drawn as rock strata. Per layer, rendered as deposits in the rock:

- lessons that visited it, marked evergreen / case (with date) / superseded
- whether a narration exists for the stage
- build rungs that touch it (from the syllabus text)
- count of recall cards currently due from it

The ladder's position line is the column's active face. Clicking a layer opens it: lessons with `obsidian://` links straight into the vault, the retrieval prompts, the Missing list.

## The weekly deposits panel

"What the week laid down," sediment metaphor throughout: new lessons per stage, digest stories tagged per stage, narrations, new Main Notes, and commits per repo phrased as what the repo gained ("smart-repetition-agent: parser now walks Fields/"). Accumulation only. A quiet week is thin sediment, which is geology, not judgment.

## Two-way

- **Recall in page:** the daily recall session runs here. Show due cards, take free-text answers, rate, reschedule via FSRS. This replaces the CLI as the primary review surface; Telegram stays for reminders.
- Later: capture a narration transcript, record which Main Note candidates were taken, draft a map-amendment proposal (written to a file for chat approval, never applied directly).

## Hard rules (the anti-evaluator boundary, non-negotiable)

Everything shown describes material, never the person. Therefore, nowhere in any view, ever: completion percentages, progress bars, streaks, session counts, days-since, comparisons to previous weeks, red or overdue styling, or any notification. Cards due is the strongest statement permitted, and it is phrased about the material. The page is pull, not push: it never opens itself, never alerts, and respects that some mornings and evenings are analog. If a future feature would make the person feel assessed, it is wrong regardless of how useful it looks, per the vault's 2026-08-01 declaration.

## Phases, mapped to build-hour rungs

1. **Parser first (shared with the SRA revival, already underway):** read `Fields/<Subject>/Lessons/`, the syllabus (stages, position, visited, Missing), and lesson retrieval prompts into models. This is the same code the recall engine needs; Strata is a second consumer, not a detour.
2. **The column:** FastAPI app, one endpoint, one HTML page (server-rendered, no build tooling), the column and layer detail with `obsidian://` links.
3. **Recall in page + weekly deposits:** wire FSRS review through the page; add the deposits panel including git reading (`git log --since` on configured repos).
4. Later, only if the page earns daily opens: a native wrapper (menu bar). Not before.

## Engine rework (the card system underneath, decided 2026-08-09)

The scheduler stays FSRS; the card layer around it changes.

**Three card sources, provenance marked on every card.**
- `lesson`: the five retrieval prompts every lesson now ends with, ingested automatically. The seed deck: what the material considers essential, guessed at authoring time.
- `session`: minted at the end of a work session, at most one or two, from whatever confusion that session resolved. Demand-side: a spot where the operator's model was demonstrably wrong an hour earlier is the highest-value card that exists.
- `narration`: the left-behind list from a stage narration, each gap becoming a card.

The provenance ratio is a signal about the material, not the operator: if session cards keep outnumbering lesson cards on one stage, that stage's lessons were aimed wrong, and the weekly pipeline evaluator may propose against it.

**Learning steps.** A new or failed card repeats within the same session until rated good, then graduates to the FSRS decay schedule. Fixed repeat counts are not used anywhere else: FSRS already schedules each card by its own measured decay, and a flat "x times" would treat every card as equally forgettable, which is the assumption FSRS exists to replace.

**Cards are anchored to their source.** Every card stores its source file path and heading. A card whose source is gone or superseded retires automatically instead of quizzing dead material.

**Stage tags.** Every card carries its syllabus stage, which is what lets the column show due counts per layer.

**Interleaving.** A session mixes due cards across stages rather than blocking one topic. Mixed practice feels worse and retains better; the feeling is not the measurement.

**Card types.** Free-text concept cards (existing, AI-scored) and code-recall cards: a function signature or contract fragment shown, the body rewritten cold, a diff shown after. The old deck (cards citing the course deleted 2026-08-05) is archived, not migrated.

## Out of scope, permanently

Cloud anything, accounts, telemetry, auto-posting, reading Therapy/Health/People folders, and any metric about the operator.
