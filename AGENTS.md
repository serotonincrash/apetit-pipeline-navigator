# Working in this repo

Read this before writing code or text here. It is copied from the spec (`docs/spec.md`), which is
the source of truth for what to build. Terms come from `docs/glossary.md`.

## How work is split

- One task per branch and worktree. Set one up with `scripts/worktree.sh up <name> <slot>`.
- Touch only the files your task names. Migrations, lockfiles, the step registry
  (`backend/src/navigator/steps/__init__.py`), the API router list and the glossary have one
  owner each; ask instead of editing them.
- Don't add dependencies. Ask.
- Never run `docker compose down -v`, and never touch another worktree's database or bucket.
- A task is done when its "done when" check passes and `pre-commit run --all-files` is clean.

## Commands

From `backend/`:

- `uv run pytest -m golden` runs the golden-number tests (no services needed).
- `uv run pytest -m api` runs the API tests (needs the dev Postgres and MinIO).
- `uv run ruff check . && uv run ruff format --check . && uv run pyright`
- `uv run alembic upgrade head`
- `uv run uvicorn navigator.api.main:app --port $API_PORT` and `uv run python -m navigator.worker.main`

## Coding standards

Much of the code will be written quickly, partly by coding agents, and five people have to read and change it within two days. The aim is code that is small, plain and consistent, and screens that each look built for their job.

Tools, all run by pre-commit hooks before each commit:

| Area | Tool | Setting |
| --- | --- | --- |
| Python lint and format | ruff | Rule sets E, F, I, B, UP, SIM and RUF; line length 100; `ruff format` |
| Python types | pyright | Strict on `navigator/`, basic on `tests/` |
| TypeScript lint and format | Biome | Recommended rules, `noExplicitAny` as an error |
| TypeScript types | tsc | `strict` and `noUncheckedIndexedAccess` on |
| Golden tests | pytest | The golden-number tests from Testing |

The standards in this section and Writing standards, plus the glossary, are copied into `AGENTS.md` at the repo root, so every coding agent works from the same rules.

### Backend

1. Steps are pure. A step reads only from `ctx`, `inputs` and `params` and returns a `StepResult`. No files, environment variables or database calls inside a step; the runner does all of that. This is what makes golden tests and replays possible.
2. Numbers that change a result are assumptions or params, never literals in a step. The shrinkage strength, the soil water capacities and the replacement premium all live in config or the assumption table.
3. Every public function has type hints. Pydantic models sit at the API edge; plain dataclasses or DataFrames inside.
4. Names come from the domain and the glossary: `parcel`, `farm`, `season`, `shortfall`. No `data`, `df2`, `tmp`, `result_final`, `utils.py`, `helpers.py` or `*Manager`.
5. No abstraction ahead of need. No base classes, registries or options until a second real use exists. Three similar lines are better than one clever helper.
6. No catch-all `except`. Let a step fail; the runner records the error. Catch only to add context and raise again.
7. Comments say why, not what. No commented-out code, no `TODO` without a name, and no comments that narrate an edit ("Added X", "Updated to use Y").
8. Logging goes through the structured logger, never `print`.
9. New dependencies need the team's agreement and go into `uv.lock`.

### Frontend

1. Types for API data come from the generated client. Never write a type by hand that the OpenAPI already describes.
2. Server data lives in TanStack Query. Component state is only for things like an open panel or a selected row.
3. Components come from shadcn/ui and are styled with the theme's Tailwind tokens. No inline styles and no arbitrary values such as `w-[317px]`.
4. One component per file, named after what it shows: `ProposalRow`, `MetricSources`, `RiskByCropChart`.
5. Numbers, dates and euros go through one formatting module, so €36k, 2.6% and 2041–2060 look the same on every screen.
6. Charts go through a few shared wrappers over Recharts, so axes, scenario colours, tooltips and number formats match everywhere.

### UI patterns to avoid

Generated interfaces tend to look alike: every page a grid of identical cards with an icon, a big number and a grey caption; gradient headers; badges and shadows on everything; one purple accent; a spinner wherever data loads. The app avoids that with these rules:

1. Each screen starts from its main task in the App screens table, not from a card grid. Data review is a dense table with a side panel for evidence. The risk view is a chart with a breakdown table under it. The report is a single reading column.
2. Tables are the default for records. Numbers are right-aligned in tabular figures, with the unit in the column header rather than in every cell.
3. Stat tiles only for headline numbers, at most four on a screen, and each opens its metric's sources.
4. Colour carries meaning. One accent for primary actions, one fixed colour per scenario used in every chart, and status colours only for statuses (run states, proposal decisions). Everything else is neutral.
5. Borders or shadows, not both. One corner radius across the app.
6. Icons only where they add meaning, always with a label or tooltip. No decorative icons, no emoji.
7. Loading states match the layout: skeleton rows for tables, and the run timeline fills from live events instead of showing a spinner.
8. Every screen has its own empty and error state, written to the UI copy rules.
9. Before a screen counts as done, put it next to the others. If two screens doing different jobs look the same, rework one of them.

## Writing standards

Three kinds of text reach people: the annotations on steps and sections in the recipe code, the text the agents write at runtime, and the copy in the web app. The readers are the two specialists and Apetit's management. They know farming and the numbers, and most of them don't read code.

Rules for all three:

1. Plain words and short sentences, one idea per sentence. Write "farms that grow peas", not "pea-cultivating entities".
2. Name the real thing: the table, the column, the farm, the year. "Fixes 18 parcels whose area is in square metres" says more than "Handles data inconsistencies".
3. Every number has a unit and says where it came from: "€36k a year (step 9, SSP5-8.5)". Round to what the data supports: two significant figures for euros, one decimal for percentages.
4. State uncertainty once, where it matters, as a range. Don't spread hedges through the text ("may potentially", "could possibly").
5. Active voice, present tense. "The step drops parcels with no area", not "Parcels with no area are dropped".
6. One term for one thing, taken from `docs/glossary.md`. If a screen says "shortfall", the annotation and the report say "shortfall" too.
7. Things to leave out:
   - Em dashes. Use a full stop, a comma or brackets.
   - Symbol shorthand in sentences, such as `×`, `→`, `≠`, `~` and `≥`. Write "times", "to", "about", "at least". Symbols are fine in formulas, tables and code.
   - Bold labels at the start of a sentence or list item.
   - "Not X but Y" and "It's not just X, it's Y" constructions.
   - Openers and closers that say nothing: "It's worth noting", "Importantly", "In summary", a last line that repeats the paragraph.
   - Filler words: genuinely, honestly, straightforward, seamless, robust, leverage, delve, crucial, comprehensive.
   - Emoji.
   - Inflated words: highlights, underscores, showcases, plays a key role, landscape, ensure, foster, empower, unlock, insights, actionable.
   - Vague amounts: various, several, a number of, "and more". Give the count. Use "significant" only in its statistical sense.
   - Lists of three by habit, such as "fast, reliable and transparent", where one word would do.
   - Headings written as questions or with a colon subtitle ("Why it matters", "Risk: a closer look").
   - Title Case, ALL CAPS and exclamation marks.

### Code annotations

Each `@step` has a summary of at most 40 words: what goes in, what comes out, and why the step exists. Each `section` has one sentence of at most 25 words saying what it does in farming or business terms.

- Describe what and why, never how the Python works. "Loops over rows and merges" means nothing to the reader.
- When a section uses an assumption, name it, so the app can link to it.
- Annotations are static text. No numbers computed at run time go in them; the app shows the step's metrics beside them.
- Write the annotation with the code and change it whenever the code changes.
- Start with the verb ("Picks", "Drops", "Prices"). Skip stock openings such as "This step is responsible for", "Helper that" or "Handles".

```python
@step("tune_calendar", summary="Picks the sowing temperature and maturity length for each region and crop, so the modelled harvest lands inside the delivery dates in the ERP data.")
def tune_calendar(ctx: RunContext, inputs: dict[str, Artifact], params: dict) -> StepResult:
    with section("score settings", "Tries every setting in the grid and scores how well each one explains past yields."):
        ...
    with section("apply delivery check", "Rejects settings whose harvest falls more than 5% outside the delivery window."):
        ...
```

Too vague: "Processes calendar data." Too technical: "Grid search over (M, T) with LOYO CV, filtered by ERP prior."

### Agent output

Each agent returns structured JSON, and its free-text fields follow the rules above with these limits:

| Agent | Field | Limit | What it must contain |
| --- | --- | --- | --- |
| Fix proposer | explanation | 60 words | What looks wrong, the evidence (record keys), the proposed fix, what happens if it is rejected |
| Review explainer | explanation | 80 words | Why the rule fired, with the values that made it fire |
| Action proposer | rationale | 80 words | The driver it targets, how the override models it, the cost and its source |
| Report drafter | each paragraph | 120 words | Findings as citation tokens to metrics, never typed numbers |

- Every claim about the data cites a record key or a metric id. Reviewers reject a claim with no citation.
- Agents describe cost, risk and options. Choosing is for people, so a draft says "would remove", not "we recommend", unless a reviewer has already approved that action.
- These rules and two good examples go into each agent's prompt. When a reviewer rejects text for its writing, they say so in the comment, and the team uses those comments to improve the prompt.
- Agents write about the data in the third person. No "I", no "Here is", no "Based on the data provided", no restating the task, no apology and no offer of more help at the end. They never say they are an AI or name a model.

### UI copy

- Use the farming and business words, not internal names. Show "High emissions (SSP5-8.5)", not `ssp585`; "Turnip rape", not `turnip_rape`.
- Buttons name the action: "Approve fix", "Run what-if", "Publish report". Never "Submit" or "OK".
- Sentence case for every label, heading and button.
- Empty states say what is missing and what to do: "No proposals yet. Start a run to check the farm data."
- Errors say what happened and what the person can do next. No stack traces; the data specialist gets the run id to copy.
- Keep implementation details out, in the copy and in annotations, since the app shows both. That means no provider or model names ("Gemini", "Powered by"), no service names (Postgres, MinIO, DuckDB), no internal terms (artifact, step run, payload, SSE) and no notes about the demo setup or what could change later ("demo mode", "can be switched to Azure"). Those belong in the docs.
- Text an agent wrote is labelled in plain words, such as "Suggested by a data check" or "Suggested by the assistant". The model that wrote it is kept in the call log, not on screen.
- No sparkle icons or magic-wand buttons for AI features, and no "AI-powered", "smart" or "intelligent" labels.
- No marketing voice in a working tool: "Unlock insights", "Welcome back!", "Your dashboard is ready".
- No cute or empty errors: "Oops!", "Uh oh", or "Something went wrong" with nothing after it.
- No placeholder content: lorem ipsum, made-up names, "Coming soon" buttons, features shown but disabled. If it isn't built, it isn't on screen.
- Helper text only where it adds something the label doesn't. A tooltip that repeats its label goes.
- Absolute dates for anything in the audit trail, such as decisions and published reports. Relative times ("2 minutes ago") only for runs in progress.
