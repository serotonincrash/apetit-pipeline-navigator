# Climate risk platform: build spec

Nov 7, 2026 · @Khanh

## Goal and scope

We build a working climate-risk platform for Apetit. Raw data goes in untouched. Recipes check it, clean it and turn it into farm climate risk in euros, with actions that reduce it. A person approves the data fixes and the results before anything is published.

In scope for the hackathon:

- Platform core: a recipe runner, lineage from every number back to its source rows, two review queues and one app.
- Recipe 1, farm climate risk, end to end. This is the part the brief singles out: business risks and costs under different climate scenarios, focusing on farming conditions.
- Recipe 2, a thin energy-meter check, to show the same flow works on corporate data and feeds the GHG calculation.
- LLM agents that propose fixes, explain review items and draft the report. The calculations themselves stay deterministic.
- Documentation: usage instructions, a one-page method note and how the platform maps onto Microsoft Fabric.

Out of scope for now, each a later recipe on the same base: SBTi target pathways, the full GHG inventory, the SBTN catchment ranking and the C1 submission file.

The brief judges automated reporting, use of the frameworks and climate scenarios, reliable data handling, a clear audit trail, and useful insight about future scenarios. It asks for a working AI solution with documentation and usage instructions, and values usefulness and traceability over the number of topics covered.

## Users and the two review steps

Every change to the data and every published result passes a named person. Nothing reaches the cleaned tables or the report on an LLM's word alone.

| User at Apetit | What they do in the platform | Review step |
| --- | --- | --- |
| Data specialist (IT, data owner) | Approves, edits or rejects proposed data fixes; writes or approves checks; watches runs and manages access | Data review |
| Sustainability specialist | Checks risk figures, assumptions and recommended actions; changes assumptions without writing code; approves the report for publishing | Results review |
| Sourcing manager | Reads the action options for their crops and regions; comments before approval | Results review (comments) |
| Management | Reads the published report and follows any number back to its sources | None |

The two audiences we design for are the sustainability specialist, who is fluent with the numbers but doesn't code, and the data specialist, who owns the data flows and systems. Every screen is built for one of them, and neither should need to know that Python sits behind the app.

How the two steps work:

- Data review: rules and agents write proposals. Each has the record, the old and new value, the evidence and a plain-language explanation. A fix is `open` until a person decides; the latest decision makes it `approved` (an edit counts as approved, with the edited value) or `rejected`. A flag stays `flag` unless a person rejects it. The cleaned tables are rebuilt from the raw data plus approved fixes only.
- No automatic approval. Every fix needs a person's decision. To save time, a reviewer can approve or reject all of one rule's proposals at once; that records one decision per proposal.
- Decisions carry over between runs. A decision points at the proposal's fixed key (rule, record key and field). The next run's check step writes the same proposal again, and it arrives with its decision already applied. A run never overwrites a person's decision.
- Results review: a run's results start as a `draft`. Approval freezes them under the run's id, and publishing makes the report visible. A later run never changes a published result; it creates a new one.
- Only the two specialists make decisions, so the persona switcher offers those two. The sourcing manager comments on action options; management reads the published report.

## Questions to ask Apetit

The answers decide how the screens work for each audience. The two audiences map onto Apetit's two contacts: the sustainability questions go to the sustainability contact, the data questions to the IT contact.

For the sustainability specialist (fluent with the numbers, doesn't code):

1. Which decisions and reports would this feed, and how often: the annual GHG report, CSRD, SBTi targets, sourcing planning?
2. Where do you work today, in Excel or a reporting tool, and what would you want to export into it?
3. Which assumptions would you want to change yourself, without a developer: prices, contract volumes, the choice of scenario?
4. What do you need to see before you trust a modelled number: its drivers, a range, the source records? How should uncertainty be shown?
5. What does an auditor ask you for today, and who signs off on what?

For the data specialist:

1. How does the data arrive today: ERP extracts, meter systems, supplier files? How often, and from which systems?
2. Who finds and fixes data errors now, and how should automated fix proposals reach them?
3. Should new checks be written as code, or set up as rules without code?
4. What are the constraints: the Azure tenant, sign-in through Entra ID, where data may be stored, and whether data may be sent to an LLM, through Azure OpenAI or otherwise?
5. How should runs, model versions and access rights be managed and monitored?

For both:

1. How often would you open this: weekly, monthly, once a year? Who else needs access, for example the sourcing manager?
2. What would make you stop using it?

One question still affects the numbers: how much spare freezing capacity Bjuv has in the harvest weeks. That decides whether the Foodhills hedge from step 9 is real, and can go to the sustainability contact as a side question.

## Architecture

&#91;embedded content: recipe 1 flow · 8 stages, 2 human approvals\]

Raw files are checked, a person approves the fixes, and the cleaned tables feed the yield model. The risk results then wait for a second approval before the report is published. Every stage writes to the lineage store, which is how any number in the report opens down to its source rows. The app sits on top of all of it: the review screens are where the two approvals happen.

## Backend architecture

Five services behind a reverse proxy, plus a sandbox: a worker runs every recipe step, the API only queues runs and serves results, Postgres holds the platform's state and run queue, SeaweedFS holds the data, the web service serves the app, and the sandbox runs approved rule code written by an agent. These decisions were taken by the team on 7 November.

&#91;embedded content: backend containers · 4 services, 1 external API\]

The web app talks only to the API. The API writes runs into the Postgres queue and records decisions; the worker claims runs from the same queue, writes results back, stores artifacts in SeaweedFS and calls Gemini for the agent steps. The API never runs a step itself: it reads results straight from SeaweedFS with DuckDB.

| Area | Decision |
| --- | --- |
| Backend | Python with FastAPI. The API and the worker import the analysis code directly; nothing runs as a subprocess. |
| Containers | Docker Compose: API and worker (same image, different command), Postgres, SeaweedFS, web, a Caddy reverse proxy in front, a sandbox for rule code written by an agent, and a one-off seed job. |
| Platform tables | Postgres, through SQLAlchemy with Alembic migrations. |
| Run queue | The worker polls the `run` table and claims a run with row locking (`FOR UPDATE SKIP LOCKED`). One run at a time. |
| Artifacts | Parquet files in SeaweedFS, through the S3 API. SeaweedFS replaced MinIO, whose official image is no longer public on Docker Hub; the code only speaks S3, so any S3 store fits. |
| Reading results | The API queries the Parquet artifacts in SeaweedFS with DuckDB on each request, including drill-down to source rows. |
| Lineage | Artifact plus filter: each metric records its source artifacts and, for each, a filter of column-value pairs that selects its contributing rows (see Lineage filter under Data model). |
| Recipes | Pure Python. The notebook logic is refactored into step functions. A `@step` decorator and named `section` blocks inside steps carry plain-language annotations, which the app shows next to each run. |
| Reusing work | Normal runs rerun every step. A what-if run starts from an approved run's artifacts and reruns only the steps after its override. |
| Live progress | REST for everything, plus a server-sent event stream per run for step and section progress. |
| LLM | Gemini through an AI Studio API key, using Google's `google-genai` SDK behind a thin internal wrapper: prompt in, validated JSON out, every call logged. |
| Data sent to the LLM | During the hackathon only the synthetic challenge package goes to Gemini. Real Apetit data waits for Apetit's written answer on LLM use; the wrapper lets them switch provider. |
| LLM failures | Output that fails its JSON schema, a guardrail or the prose check goes back to the model with the error, at most twice. After that the call is recorded as failed and shows in its queue. A failed report draft produces no draft, never a partial one. If the key fails or the quota runs out, the wrapper switches to the fake model the tests use, and the call log records the switch. |
| Agent rule sandbox | Rule code written by an agent runs only after a person approves it, and only in a separate sandbox service: no network, a read-only file system, and CPU, memory and time limits. The worker sends it the input table and the rule code, and gets proposals back as JSON that must pass the proposal schema. Rules written by people run in the worker. |
| Sign-in | None for the hackathon. A persona switcher picks the role and the name recorded on decisions. |
| Code and tools | A new monorepo; uv for Python dependencies; golden-number tests (each step reproduces the notebooks' results) plus tests of the main API flows. |
| Configuration | A git-ignored .env file read by Docker Compose and loaded into a typed settings object with pydantic-settings; a committed .env.example lists every variable. |
| Logging | Structured JSON logs to stdout from the API and worker. Run, step and section events are also stored in Postgres and streamed to the app. |
| Ids | Prefixed by record type, followed by a time-sortable unique id: run\_…, step\_…, art\_…, prop\_…, dec\_…, met\_…, act\_…, opt\_…, rs\_…, asm\_…, ins\_…, rep\_…, call\_… (the full list is in ids.py) |
| Seeding data | A one-off seed job at startup uploads the unzipped challenge package to SeaweedFS and records each file with its checksum. Runs read from SeaweedFS only. The seed job also loads the action catalogue and records a Catalogue policy approval for each catalogue action. |
| Demo hosting | The same Compose stack on a Vultr VM, with Caddy providing HTTPS automatically and one URL for web and API. |
| Demo access | One shared username and password at the Caddy proxy, so the public URL can't be used to start runs on the team's Gemini key. |
| Production LLM | Apetit's choice. Any provider plugs in behind the wrapper if it offers structured JSON output, per-call logging and data-handling terms Apetit accepts. |

## Repo layout

One new monorepo with the backend, frontend, notebooks and infrastructure side by side. The analysis modules move out of the notebooks folder into the backend package, and the notebooks import them from there, so the app and the notebooks always run the same code. The Python package is called `navigator`, which avoids clashing with Python's built-in `platform` module.

```text
climate-nature-navigator/
├── backend/
│   ├── pyproject.toml, uv.lock
│   ├── alembic/                  database migrations
│   ├── src/navigator/
│   │   ├── settings.py           typed settings from .env (pydantic-settings)
│   │   ├── api/                  FastAPI app, one router per screen, SSE stream
│   │   ├── worker/               queue loop: claim a run, execute its recipe
│   │   ├── db/                   SQLAlchemy models for the platform tables
│   │   ├── storage/              S3 client; DuckDB queries over Parquet
│   │   ├── recipes/              recipe definitions, step registry, @step and section
│   │   ├── steps/                step functions refactored from the notebooks
│   │   ├── analysis/             cropweather, yieldcv, yieldmodel, climateproj, riskprice, actions
│   │   ├── agents/               fix proposer, explainer, action proposer, report drafter, prompts
│   │   └── llm/                  Gemini wrapper, JSON validation, call log
│   └── tests/
│       ├── golden/               each step reproduces the notebooks' results
│       └── api/                  main API flows against test Postgres and SeaweedFS
├── frontend/
│   ├── package.json, biome.json
│   └── src/
│       ├── routes/               one route per screen (TanStack Router)
│       ├── components/           shadcn/ui components, charts, the metric drill-down panel
│       └── api/                  client generated from the OpenAPI contract
├── notebooks/                    the analysis notebooks and their versioned results/
├── config/
│   └── actions/catalogue.json    action specs
├── infra/
│   ├── docker-compose.yml
│   ├── Caddyfile
│   ├── seed/                     the seed job
│   └── .env.example
├── scripts/
│   └── worktree.sh               set up or remove a worktree with its own database and bucket
├── docs/                         method note, Fabric mapping, usage instructions, glossary.md
├── AGENTS.md                     coding and writing standards for coding agents
└── .pre-commit-config.yaml       ruff, pyright, Biome, tsc, golden tests
```

## Run lifecycle and live events

The API queues a run, the worker executes it, and its progress streams to the app as it happens. Changes to data and results take effect only through approvals and new runs; a run never pauses to wait for a person. Review and publishing are states of the result set, not steps of a recipe.

| Run kind | Starts from | Steps executed |
| --- | --- | --- |
| Full | The raw package in SeaweedFS and the fixes approved so far | Every step of the recipe |
| What-if | An approved run and one approved action spec | Only the steps from the action's override point; earlier steps reuse the parent run's artifacts |
| Report | A succeeded run's result set | Only the report drafter. Each report run writes a new numbered draft to the report table; drafts are never overwritten |

States:

- Run: `queued`, then `running`, then `succeeded` or `failed`. On startup the worker marks any run left `running` by a crash as `failed`.
- Step: `pending`, `running`, then `succeeded`, `failed`, or `reused` (a what-if run's steps before its override).
- Result set: created as `draft` when a run succeeds, then `in review`, `approved` and `published`. A later published set marks the earlier one `superseded`.
- Proposals: written during the check steps. The run builds cleaned tables from the fixes approved so far; the Data review screen offers "run again with approved fixes" once new decisions are in.

The worker polls the `run` table every few seconds, claims the oldest queued run with `FOR UPDATE SKIP LOCKED`, and executes its steps in order. Each step writes its `step_run`, artifact, proposal and metric rows, and emits events.

Events are stored in a `run_event` table and streamed at `GET /api/runs/{id}/events` as server-sent events. A reconnecting browser sends the last event id it saw and gets the rest from the table.

| Event | Sent when | Carries |
| --- | --- | --- |
| `run.status` | A run changes state | Run id, new state |
| `step.started` / `step.finished` | A step starts or ends | Step name, its annotation, duration, status |
| `section.started` / `section.finished` | A named section inside a step starts or ends | Section annotation, duration |
| `proposal.created` | A check step or agent writes proposals | Count per rule |
| `run.finished` | The run ends | Final state, result set id |

## API

Twenty-seven endpoints, the 26 rows below plus one for marking action options, all under `/api`, grouped by the screen that uses them. FastAPI generates the OpenAPI contract from them, and the frontend client is generated from that contract. The field-level contract is `docs/openapi.json`, generated from the code; regenerate it after every API change. Every write takes the current persona's name, sent by the app in an `X-Persona` header, and records it.

| Screen | Method and path | What it does |
| --- | --- | --- |
| All | `GET /api/health` | Liveness check for Caddy and Compose |
| All | `GET /api/personas` | Personas for the switcher: role and display name |
| Runs | `POST /api/runs` | Queue a run: recipe, kind (full or what-if), parent run and action id for a what-if, assumption overrides |
| Runs | `GET /api/runs`, `GET /api/runs/{id}` | List runs; one run with its steps and their annotations |
| Runs | `GET /api/runs/{id}/events` | Server-sent event stream of the run's progress |
| Runs | `GET /api/artifacts/{id}` | An artifact's metadata: step, layer, row count, content hash |
| Runs, risk | `GET /api/artifacts/{id}/rows` | Rows of an artifact, filtered and paged, read with DuckDB |
| Runs, risk | `GET /api/artifacts/{id}/export` | The filtered rows as an Excel file |
| Data review | `GET /api/proposals`, `GET /api/proposals/{id}` | Proposals filtered by rule, table and status; one with its evidence and explanation |
| Data review | `POST /api/proposals/{id}/decisions` | Approve, edit or reject one proposal, with a comment |
| Data review | `POST /api/proposals/decisions` | Approve or reject many proposals in one call (for example, all of one rule). It writes one decision row per proposal, exactly as if each were decided on its own |
| Rule proposals | `GET /api/rules`, `POST /api/rules/{id}/decisions` | Rules with their backtest; approve or reject an agent's rule |
| Risk view | `GET /api/result-sets`, `GET /api/result-sets/{id}/metrics` | Result sets of a run; metrics filtered by region, crop, scenario and NGFS scenario |
| Risk view | `GET /api/metrics/{id}/sources` | Drill-down: source artifacts, the lineage filter, contributing rows, corrections applied and assumptions used |
| Risk view | `GET /api/assumptions` | Assumptions behind a result set, with their sources; changing one means queuing a run with overrides |
| Actions | `GET /api/actions`, `POST /api/actions/{id}/decisions` | Catalogue and proposed action specs; approve one to run |
| Actions | `GET /api/result-sets/{id}/action-options` | Priced what-if results for comparison |
| Actions | `POST /api/action-options/{id}/decisions` | Mark a priced option recommended, considered or rejected, with a comment |
| Report | `POST /api/result-sets/{id}/report` | Ask the report drafter for a draft, queued as a report run on the worker |
| Report | `GET /api/result-sets/{id}/report` | The latest draft or the published report: its text with metric tokens resolved, its insights, and the lineage of every number |
| Report | `POST /api/result-sets/{id}/decisions` | Move a result set to in review, approved or published |
| Report | `GET /api/result-sets/{id}/report/export` | The published report as Markdown. PDF comes from the browser's print, with every disclosure group open |

## Frontend

A React single-page app, built with Vite and TypeScript, that only talks to the API. It is designed so the sustainability specialist never meets code and the data specialist sees every detail of a run.

| Part | Choice |
| --- | --- |
| Components and styling | shadcn/ui on Tailwind |
| Routing | TanStack Router, with typed routes and search parameters (filters live in the URL, so a filtered view can be shared as a link) |
| Server data | A client generated from the OpenAPI contract, with TanStack Query for caching, refetching and loading states. The generator, for example orval or openapi-typescript, is picked when scaffolding. |
| Charts | Recharts |
| Live progress | The browser's EventSource on the run's event stream |

Pages, one route per screen:

| Route | Screen |
| --- | --- |
| `/runs`, `/runs/$runId` | Runs, and one run's live timeline of steps and sections with their annotations |
| `/review/data` | Data review queue; where the data specialist lands |
| `/review/rules` | Rule proposals |
| `/risk` | Risk view, filtered by region, crop, climate and NGFS scenario; where the sustainability specialist lands |
| `/actions` | Action catalogue and priced what-ifs |
| `/report/$resultSetId` | The interactive report: drafted text, a dashboard of its key metrics and insights, and each number's lineage in a disclosure group; review and publishing |

Three things every screen shares:

1. A persona switcher in the header picks the data specialist or the sustainability specialist and the name recorded on decisions. It is remembered in the browser and sent as the `X-Persona` header.
2. Every result number is rendered by one component that opens a side panel on click. The panel shows where the number came from: source artifacts, the filter, the contributing rows, corrections applied and the assumptions used.
3. Assumptions are edited in forms, and saving queues a new run with those overrides; tables export to Excel.

## Deployment and demo

The same Docker Compose file runs on a developer's laptop and on the Vultr VM. Only Caddy is reachable from outside; everything else talks on the internal Compose network.

| Service | Image | Role | Persistent data |
| --- | --- | --- | --- |
| `caddy` | Caddy | HTTPS certificate, shared password, routes `/api` to the API and everything else to the web app | Certificates |
| `web` | Built frontend | Serves the compiled React app as static files | None |
| `api` | Backend image | FastAPI under uvicorn | None |
| `worker` | Backend image | The run queue loop | None |
| `sandbox` | Backend image | Runs approved rule code written by an agent, with no network, a read-only file system, and CPU, memory and time limits | None |
| `postgres` | Postgres | Platform tables, run queue, run events | Database volume |
| `seaweedfs` | SeaweedFS (chrislusf/seaweedfs, S3 on port 8333) | Raw package, artifacts | Object volume |
| `seed` | Backend image | One-off at startup: runs the Alembic migrations, then uploads the challenge package to SeaweedFS with checksums and loads the action catalogue; exits | None |

Environment variables, listed in `infra/.env.example`:

| Variable | What it sets |
| --- | --- |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | The AI Studio key and the model the agents use |
| `DATABASE_URL`, `POSTGRES_PASSWORD` | Postgres connection and password |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ENDPOINT`, `S3_BUCKET` | S3 credentials, endpoint and bucket |
| `PACKAGE_DIR` | Where the seed job finds the unzipped challenge package |
| `DOMAIN` | The domain pointed at the VM, for Caddy's certificate |
| `BASIC_AUTH_USER`, `BASIC_AUTH_HASH` | The shared demo login (the password stored as a hash) |
| `LOG_LEVEL` | Log detail |

On the Vultr VM:

1. Point a domain or subdomain at the VM, and open only ports 80 and 443 in the firewall.
2. Copy the repo and the unzipped package to the VM, and fill in `.env`.
3. Run `docker compose up -d`. The seed job loads the data; Caddy fetches the certificate.
4. Queue one full run of each recipe, review and publish its results, so judges find a complete example waiting.
5. After the judges have used the app, run `scripts/reset_demo.sh`. It empties the database and the bucket, reseeds the package, and queues and approves one full run again, so the VM is back in its prepared state.
6. Size the VM after a test run there; SeaweedFS stays internal.

## Local development

Several coding agents work on one computer at once, each in its own git worktree on its own branch. They share one Postgres and one SeaweedFS per computer, and each worktree gets its own database and bucket inside them.

The `dev` profile of the Compose file starts only Postgres and SeaweedFS. In each worktree the API, the worker and the Vite dev server run on the host, with `uv run` and `npm run dev`, against that worktree's database and bucket.

`scripts/worktree.sh up <name> <slot>` sets up a worktree in one command:

1. Adds the git worktree and branch.
2. Creates the databases `navigator_<name>` and `navigator_<name>_test`, and the buckets `navigator-<name>` and `navigator-<name>-test`.
3. Writes the worktree's `.env` with those names and its ports.
4. Runs `uv sync`, `npm install` and the Alembic migrations.
5. Copies the raw package into the bucket from a shared `navigator-seed` bucket, which the seed job fills once per computer.

`scripts/worktree.sh down <name>` drops the databases and buckets and removes the worktree.

Ports per slot, so worktrees never collide:

| Service | Port |
| --- | --- |
| Postgres (shared) | 5432 |
| SeaweedFS S3 API (shared) | 8333 |
| API in slot n | 8100 + n |
| Vite dev server in slot n | 5200 + n |

Some files break when two branches change them at once, so each has one owner:

| File | Rule |
| --- | --- |
| Alembic migrations | Only the core owner writes them, so there is never more than one head |
| Generated API client | Regenerated on main after each API change, never merged by hand |
| `uv.lock`, `package-lock.json` | Agents don't add dependencies. They ask, and one person adds them |
| Step registry, router list, glossary | One branch at a time |

Agents never run `docker compose down -v` or touch another worktree's database or bucket. Branches merge into main one at a time, and the others rebase onto it.

## Testing

Two kinds of test, both run with pytest. Golden-number tests prove the refactored steps still give the notebooks' answers; API tests prove the main flows work end to end.

Golden-number tests compare each refactored step with the notebooks' results: fingerprints in backend/tests/golden/reference/ for tables the notebooks don't keep, and the versioned files in `notebooks/results/`:

| Step | Must reproduce |
| --- | --- |
| Check farm data | The corrections log: 18, 44, 85, 195 and 6 proposals for rules R1 to R5, with no decisions written by the step. The test then approves the R1, R2, R3 and R5 fixes as a reviewer would, to match the notebook |
| Tune calendar | The chosen settings in `calendar_choice.csv` |
| Fit yield model | The coefficients and backtest errors in `yield_model.json` and `yield_backtest_summary.csv` |
| Project yields | The yield changes and bad-year chances in `yield_projection_2041_2060.csv` |
| Price risk | The expected costs in `climate_risk_eur.csv`, to the cent |
| Compare actions | The cost removed per action in `action_options.csv` |

API tests run against the worktree's own test database and bucket in the shared Postgres and SeaweedFS, emptied at the start of each test session, with the LLM replaced by a fake model that returns fixed JSON:

1. Queue a full run, follow its event stream, and see it succeed with a draft result set.
2. Approve a proposal, run again, and see the cleaned table change.
3. Open a metric's sources and get its contributing rows.
4. Approve an action and run it as a what-if from an approved run; see only the later steps executed.
5. Draft, approve and publish a report, and see every number resolve to a metric.

The golden tests run in the pre-commit hook on every commit. They start from the raw package and chain the steps, so they never depend on notebook outputs. The API tests run before each deploy to the VM.

## Writing standards

Three kinds of text reach people: the annotations on steps and sections in the recipe code, the text the agents write at runtime, and the copy in the web app. The readers are the two specialists and Apetit's management. They know farming and the numbers, and most of them don't read code.

The rules are checked automatically. `scripts/check_prose.py` looks for em dashes, symbol shorthand in sentences, the banned words and the word limits. Pre-commit runs it on step annotations, UI strings and prompt files. The LLM wrapper runs it on every agent text, where a breach counts as a failed validation (sent back at most twice, then failed).

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
| Review explainer | explanation | 80 words | Why the rule fired, with the values that made it fire written as evidence tokens such as {{ev:ratio\_to\_median}}, never as typed numbers |
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
- Keep implementation details out, in the copy and in annotations, since the app shows both. That means no provider or model names ("Gemini", "Powered by"), no service names (Postgres, SeaweedFS, DuckDB), no internal terms (artifact, step run, payload, SSE) and no notes about the demo setup or what could change later ("demo mode", "can be switched to Azure"). Those belong in the docs.
- Text an agent wrote is labelled in plain words, such as "Suggested by a data check" or "Suggested by the assistant". The model that wrote it is kept in the call log, not on screen.
- No sparkle icons or magic-wand buttons for AI features, and no "AI-powered", "smart" or "intelligent" labels.
- No marketing voice in a working tool: "Unlock insights", "Welcome back!", "Your dashboard is ready".
- No cute or empty errors: "Oops!", "Uh oh", or "Something went wrong" with nothing after it.
- No placeholder content: lorem ipsum, made-up names, "Coming soon" buttons, features shown but disabled. If it isn't built, it isn't on screen.
- Helper text only where it adds something the label doesn't. A tooltip that repeats its label goes.
- Absolute dates for anything in the audit trail, such as decisions and published reports. Relative times ("2 minutes ago") only for runs in progress.

## Coding standards

Much of the code will be written quickly, partly by coding agents, and five people have to read and change it within two days. The aim is code that is small, plain and consistent, and screens that each look built for their job.

Tools, all run by pre-commit hooks before each commit:

| Area | Tool | Setting |
| --- | --- | --- |
| Python lint and format | ruff | Rule sets E, F, I, B, UP, SIM and RUF; line length 100; `ruff format` |
| Python types | pyright | Strict on `navigator/`, except `analysis/`, which is basic until it is typed; basic on `tests/` |
| TypeScript lint and format | Biome | Recommended rules, `noExplicitAny` as an error |
| TypeScript types | tsc | `strict` and `noUncheckedIndexedAccess` on |
| Golden tests | pytest | The golden-number tests from Testing |
| Prose | `scripts/check_prose.py` | The writing standards' banned patterns and word limits, on annotations, UI strings and prompt files |

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

## Data model

Feventeen tables hold everything the platform knows: what went in, what each step did, what people decided and what came out. Data tables themselves (raw, cleaned, features) are Parquet files registered as artifacts; these tables describe them. They live in Postgres, and the artifacts are Parquet files in SeaweedFS (see Backend architecture). In Fabric, the artifacts become Delta tables in the Lakehouse.

| Table | One row is | Key columns | Written by |
| --- | --- | --- | --- |
| `source_file` | One file from the package, as delivered | `file_id`, `path`, `sha256`, `rows`, `loaded_at` | Load step |
| `recipe` | One version of a recipe definition | `recipe_id`, `version`, `steps` (ordered list), `code_commit` | Developers |
| `run` | One execution of a recipe | `run_id`, `recipe_id`, `version`, `params_hash`, `status`, `started_at`, `finished_at`, `triggered_by` | Runner |
| `step_run` | One step inside a run | `step_run_id`, `run_id`, `step`, `kind`, `params`, `input_artifacts`, `output_artifacts`, `status`, `seconds` | Runner |
| `run_event` | One progress event from a run, streamed to the app | event\_id, run\_id, step, type, payload, created\_at | Runner |
| `artifact` | One table a step produced | `artifact_id`, `step_run_id`, `name`, `uri`, `layer` (raw, clean, feature, result), `row_count`, `content_hash` | Runner |
| `assumption` | One input value a person can question | `assumption_id`, `name`, `value`, `unit`, `source` (file and row, or document and section), `owner`, `status` | Sustainability specialist, steps |
| `proposal` | One proposed data fix or flag, as one run wrote it | proposal\_id (prop\_…), proposal\_key (rule, record key and field; the same in every run), run\_id, rule\_id, issue\_type, proposer, table, record\_key, field, old\_value, new\_value, action (fix or flag), evidence (JSON, see Proposal columns), explanation. No status column: the status comes from the latest decision on the proposal\_key. | Check steps, agents |
| `rule` | One check, written by a person or proposed by an agent | `rule_id`, `version`, `code`, `author`, `backtest` (precision and recall on labelled history), `status` | Developers, agent |
| `decision` | One decision, by a person or by a written policy a person signed off, never edited afterwards | decision\_id, target\_type (proposal, rule, action, action\_option or result\_set), target\_id (a proposal\_key for proposals), decision, edited\_value, reviewer (a person's name, or "Catalogue policy" for the seeded catalogue actions), comment, run\_id, decided\_at | Reviewers, seed job |
| `result_set` | All results of one run | `result_set_id`, `run_id`, `status` (draft, in review, approved, published, superseded), `approved_by`, `published_at` | Runner, reviewers |
| `metric` | One result number | metric\_id, result\_set\_id, name, unit, value, region, crop, scenario (climate scenario), ngfs\_scenario (transition scenario), period, lineage (see Lineage filter), assumption\_ids | Model and pricing steps |
| `action_option` | One action's priced what-if result | option\_id (opt\_…), action\_id, result\_set\_id, run\_id (the what-if run), name, region, crop, cost\_eur\_per\_yr, risk\_reduced\_eur\_per\_yr, emissions\_change\_t, assumption\_ids, confidence. Recommended, considered or rejected comes from its latest decision. | Action step, reviewers |
| `action_definition` | One action in the catalogue, or one proposed by the agent | action\_id (act\_…), name, short\_name, driver, applies\_at (step), override (one typed operation, see Actions and what-if runs), scope (region, crop), cost and its source, confidence, proposed\_by. Proposed, approved to run or rejected comes from its latest decision. | Seed job (catalogue), action proposer agent |
| `insight` | One finding that is not a priced metric, such as the Foodhills supply hedge | insight\_id (ins\_…), result\_set\_id, step, title, text (numbers only as metric tokens), metric\_ids | Model and pricing steps |
| `report` | One draft of a result set's report; every report run writes a new one | report\_id (rep\_…), result\_set\_id, run\_id, version, paragraphs (each its text with metric and insight tokens, and the call\_id that wrote it), status (draft, superseded or published), created\_at | Report runs, reviewers |
| `llm_call` | One call to the LLM | call\_id (call\_…), run\_id, agent, model, prompt\_version, input\_hash, output\_hash, attempt, status (ok, retried, failed or fake model), error, created\_at | LLM wrapper |

Rules that keep the audit trail honest:

1. Raw artifacts are never overwritten. Cleaned artifacts are always rebuilt as raw data plus approved proposals, so any run can be replayed from the same inputs.
2. Record keys use the package's formats, for example `farm_survey:FS02175`, `erp:4500002962:10` and `energy:S-SAK:2025-03:electricity`. A key means the same row in every table and screen.
3. `decision` is append-only. The current status of a proposal, rule, action, action option or result set is its latest decision.
4. Every `metric` carries enough lineage to list its contributing rows, and every number in a report points to a `metric`.

### Step contract

Every recipe step is a function with this signature, defined in `backend/src/navigator/recipes/core.py`:

```python
@step("tune_calendar", kind="model", summary="Picks the sowing temperature ...")
def tune_calendar(ctx: RunContext, inputs: dict[str, Artifact], params: Params) -> StepResult: ...
```

- `Artifact` is one table: `name`, `layer` (raw, clean, feature or result), `frame` (a DataFrame) and `artifact_id` once stored. A table's name is how later steps ask for it, and it is unique within a run.
- `RunContext` carries `run_id`, `recipe_id` and `sources`, the package files by path. Only `load_raw` reads `sources`.
- `params` are the step's params from the recipe, with any overrides queued with the run.
- The recipe definition lists the tables each step reads. The input named `proposals` is filled by the runner with this run's proposals and their current status (open, approved, rejected or flag).
- `StepResult` holds `tables` (the artifacts the step writes), `proposals` (a table with the columns below, or none), `decisions` (approvals under a policy a person signed off; recipe 1 writes none), `rules` (one row per rule: rule\_id, version, description, author, backtest), `assumptions` (each input value used, with its unit and source), and in later milestones `metrics` and `insights`.

### Proposal columns

| Column | Meaning |
| --- | --- |
| `proposal_key` | Rule, record key and field joined with a vertical bar, for example `R1\|farm_survey:FS02175\|yield_t_ha`. The same in every run. |
| `rule_id`, `issue_type` | The rule and the kind of problem, for example `R2` and `decimal_shift` |
| `table`, `record_key`, `field` | The raw table, the record in the package's key format, and the column |
| `old_value`, `new_value` | As text. Empty `new_value` for a flag. |
| `action` | `fix` or `flag` |
| `evidence` | JSON: a one-line `summary`, the `record_keys` it rests on, the `query` that reproduces it, and named `values` (for example `{"ratio_to_median": 9.8}`) that explanations cite as evidence tokens |
| `explanation` | The review explainer's text, with numbers only as evidence tokens such as `{{ev:ratio_to_median}}` |
| `proposer` | `rule R1`, or `agent:fix-proposer` with its call id |

### Lineage filter

A metric's `lineage` is a list of entries, each naming one artifact and a filter on its columns:

```json
[
  {"artifact": "art_01JC...", "filter": {"region": "FI_SW", "crop": "pea", "scenario": "ssp585", "year": {"min": 2041, "max": 2060}}},
  {"artifact": "art_01JD...", "filter": {"farm_id": ["F0012", "F0040"]}}
]
```

- Every key is a column of that artifact. A value is a single value, a list (any of them) or a range with `min`, `max` or both, inclusive. Keys combine with AND, and an empty filter means the whole table.
- The API builds the SQL itself, using only the artifact's own column names and passing every value as a parameter. Steps never write SQL into lineage.
- Corrections need no entry of their own. Every cleaned row keeps its `record_key` and `n_corrections`, so the drill-down finds the decisions applied to the contributing rows by record key.
- The side panel and the report's disclosure groups show a filter in plain words built from the glossary, for example "Pea, South-west Finland, High emissions (SSP5-8.5), seasons 2041 to 2060".

## Recipe 1: farm climate risk

Ten steps take the raw package to approved risk results on how much climate change could cost Apetit's contract farming, and what to do about it. Steps 1 to 6 are refactored into step functions (milestone 1). Steps 7 to 10 still live in the notebooks named in the table, in the monorepo's `notebooks/` folder.

| # | Step | Reads | Writes | Kind | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | `load_raw` | Package files in object storage | One raw table per package file the recipe uses | Load | Refactored from `c1_clean.ipynb` |
| 2 | `check_farm_data` | Raw farm survey, registry, parcels, crop history, 2023–24 labels | Proposals from rules R1–R5 with their backtest; later, agent proposals | Propose | Rules refactored from `c1_clean.ipynb`; agent new |
| 3 | `apply_approved` | Raw tables, this run's proposals with their status | Cleaned farm survey, registry and Foodhills tables | Transform | Refactored from `c1_clean.ipynb` |
| 4 | `spatial_join` | Parcels, weather grid, crop history, cleaned tables | Parcel-to-cell map; parcel-year table 2012–2031; farm-year training table | Transform | Refactored from `c1_clean.ipynb` |
| 5 | `tune_calendar` | Daily weather, training table, parcel-years, ERP deliveries | Crop calendar per region and crop; tuning record and choice | Model | Refactored from `c1_weather_features.ipynb` |
| 6 | `weather_features` | Daily weather, crop calendar, training table, parcel-years | Stress measures per cell, soil, crop, season and climate scenario; parcel-year and farm-year model tables | Transform | Refactored from `c1_weather_features.ipynb` |
| 7 | `fit_yield_model` | Farm-year model table | Coefficients per region and crop; backtest error by season | Model | In `c1_yield_model.ipynb` |
| 8 | `project_yields` | Model, 2025 contract parcels, weather for 1991–2020 and 2041–2060 | Yield change, chance of a bad year and shortfall distribution per region, crop and climate scenario | Model | In `c2_yield_projection.ipynb` |
| 9 | `price_risk` | Shortfalls, contract prices, import premiums, contracted volumes, emission factors | Expected cost per year and in a 1-in-10 bad year, in euros; extra emissions from replacement imports; the Foodhills insight | Transform | In `c3_risk_pricing.ipynb` |
| 10 | `compare_actions` | Risk results, approved actions, assumptions | Action options with cost, risk removed and emissions change | Model | In `c4_actions.ipynb` |

Drafting the report and publishing are not recipe steps. Drafting is a report run (see Run lifecycle and live events), and review and publishing are states of the result set.

What the new steps compute:

- `fit_yield_model`: the within-farm model already used for tuning. Log yield equals the farm's own level plus the weather and management effects. It is checked season by season on held-out years and reports its error next to the farm-average baseline.
- `project_yields`: there is only one weather run per scenario, so we build an ensemble. Take each historical season from 1991–2020, shift its temperature and scale its rain by the monthly changes in `climate_change_signals.csv` for that scenario, and recompute evaporation with the same Hargreaves formula the package uses. Run the 30 shifted seasons per cell through the features and the model, with today's parcels, management and the trend held at 2026, and simulate each season 50 times with the model's leftover error, drawn with a fixed random seed (2026; the bootstrap of differences uses seed 7). Both seeds are params, recorded as assumptions on every run, which is what lets the golden test match to the cent. A bad year is a yield under 80% of the 1991–2020 average, the package's own definition. The single delivered run for each scenario serves as a check.
- `price_risk`: contracted volume is the 2025 contract area (the parcels declared for 2025 in parcel\_crop\_history\_and\_plan.csv) times the normal yield of today's farms, from the model on 1991–2020 weather (1996–2025 weather changes it by under 2%, kept as a sensitivity). The shortfall in a season is the volume below that. Its extra cost is the shortfall times the contract price times the replacement premium, using `contract_prices_and_replacement_premiums.csv` and the import-premium paths in `transition_scenarios.csv` for each NGFS (transition) scenario, matched to its climate scenario by that file's physical\_pathway\_proxy column. Extra emissions are the shortfall times the full import emission factor, because the domestic fields are farmed either way. The factors per region and crop are in notebooks/results/import\_ef.json, from 0.31 t CO2e per tonne for carrot to 1.35 for turnip rape. Shortfalls are priced as market imports only; Foodhills supply is written as an insight (see Data model), not counted.
- `compare_actions`: each approved action spec is run as a what-if on top of the approved run, then priced (see Actions and what-if runs). On the first run the six catalogue actions are already approved, by the Catalogue policy at seeding, so the step always has something to price. The catalogue and what each action changes are under Actions and what-if runs.

Every assumption these steps use (prices, premiums, the 80% threshold, lever costs, ensemble size, random seeds) is a row in `assumption`, shown to the reviewer and changeable by starting a new run.

## Recipe 2: energy-meter check

A short second recipe proves the same runner, queue and lineage work on corporate data, and touches the GHG calculation the brief starts from. It should take one person under a day.

1. `load_raw`: `energy_meter_readings.csv` (610 monthly readings across sites and energy carriers), `goo_registry_statement.csv` and `sites.csv`.
2. `check_meters`: rules for missing months, spikes against the same month in other years, and readings entered in the wrong unit. The fix-proposer agent looks for anything else. Known seasonal peaks are not errors and must not be flagged.
3. Backtest: score the rules and the agent against the package's 2023–24 labels for this file (16 labelled issues: 6 missing months, 6 unit errors, 4 spikes).
4. `apply_approved`: cleaned readings, with gaps filled from approved proposals only.
5. `scope2_electricity`: location-based and market-based Scope 2 for electricity per site and year. It uses the grid factors in `METHODOLOGY.md` and counts guarantees of origin only when the registry statement shows them for the same year.
6. Check against the published 2023 and 2024 answer inventories in `tasks/dev/` and show the difference.

The output is a small result set: electricity use and Scope 2 per site and year, each figure traceable to meter readings and approved corrections.

## Actions and what-if runs

An action never edits the raw data. It is an override on the model's inputs, applied to a copy, which produces a what-if run next to the approved run. The difference between the two is what the action buys. It uses the same machinery as a data fix, applied at a different step.

|  | Data fix | Action |
| --- | --- | --- |
| What it changes | A raw record that is wrong | An assumption about the future: irrigated or not, which fields, sowing date |
| Where it applies | Before cleaning | At the model step, on a copy |
| Result | The approved run is rebuilt | A separate what-if run, compared with the approved one |
| Who approves | Data specialist | Sustainability specialist and sourcing |

How an action gets from idea to report:

1. Find the drivers. The risk step splits each crop's loss into its weather drivers, for example heat at flowering for Finnish pea and warmer Mays for turnip rape.
2. Propose candidates. The action proposer (an LLM agent) matches each driver to options in the action catalogue and writes each as an action spec whose override is one of the four typed operations below, with params that pass the schema. The catalogue starts from the package's lever list, plus adaptation actions that experts add. An idea no operation can express is flagged as new: it is listed for people to read, but it never runs as a what-if.
3. Approve what to run. A person picks which candidates are worth running, in a review queue like the one for data fixes. The six catalogue actions are seeded already approved, recorded as decisions by the Catalogue policy, so the first run has actions to price; step 10 refuses any it cannot price, such as irrigation for Finnish pea.
4. Run and price. The engine runs each approved action as a what-if run and prices it. The agent never calculates the effect.
5. Draft the recommendation. The report drafter writes what to do, for which crops and regions, who should own it and what it buys, with every number linked to the what-if run.
6. Results review, as for the risk figures, then the report.

An action spec, as it sits in config/actions/catalogue.json and as the proposer must write it. Status is not part of the spec; it comes from the latest decision.

```json
{
  "action_id": "A1-relocate-fi-pea",
  "short_name": "Relocate 20% of Finnish pea area",
  "name": "Move 20% of Finnish pea area from the highest-loss to the lowest-loss farms",
  "driver": "heat at flowering, Finnish pea",
  "applies_at": "project_yields",
  "override": {"type": "relocate_area", "share": 0.2},
  "scope": {"units": [["FI_SW", "pea"]]},
  "cost": {"eur_per_year": null, "source": "not in the package; reported as the break-even cost"},
  "confidence": "medium: yield effect from the model; recruitment and advisory cost unknown",
  "proposed_by": "catalogue"
}
```

The four operations the engine can run. Each is deterministic; the agent only chooses one and fills in its params.

| Operation | Params | What the engine does | Applies at |
| --- | --- | --- | --- |
| `relocate_area` | `share` (0 to 1) | Moves that share of the unit's 2025 contract area from the farms with the highest projected loss to those with the lowest | `project_yields` |
| `set_irrigated` | `value` (0 or 1) | Sets the irrigation input for every farm in scope | `project_yields` |
| `shift_sowing` | `days` (negative is earlier) | Moves the earliest sowing date and rebuilds the weather features | `weather_features` |
| `scale_feature` | `feature` (a model feature), `factor` | Multiplies that stress measure, for example heat days at flowering, by the factor | `project_yields` |

Which actions the data can price today:

| Action | Override | How well the data supports it |
| --- | --- | --- |
| Move contract area to lower-risk fields | Replace part of the 2025 parcels with lower-loss farms or weather cells | Good for yields; recruitment cost is an assumption |
| Irrigation for more potato and carrot growers | Set more farms to irrigated; cost from lever L24 | Partly: most of these growers irrigate already |
| Earlier sowing | Move the earliest sowing date 7 or 14 days | Weak: no history sown that early, frost not modelled; a labelled what-if |
| Heat-tolerant pea varieties | Reduce heat damage at flowering by an assumed share | Assumption only: no variety data |
| Finland–Sweden pea sourcing | Not run; written as an insight by step 9 | Depends on Bjuv's capacity, which is unknown |

Finnish pea and turnip rape growers never irrigate in the data, so the model has no estimate of what irrigation would do for them.

## LLM agents

Four agents do the reading and writing a person would otherwise do. None of them can change data or publish anything, and none of them types a number into a result.

| Agent | Job | Reads | Writes | Tools |
| --- | --- | --- | --- | --- |
| Fix proposer | Finds problems the rules miss in a raw table, and suggests new rules | Table schema, column statistics, samples, the rule library, labelled examples from 2023–24 | `proposal` rows with evidence; `rule` rows with code | Read-only queries on raw artifacts; the sandbox service, which backtests a proposed rule on the labels and, once it is approved, runs it |
| Review explainer | Explains each queued proposal in two or three plain sentences | One proposal and its evidence | `proposal.explanation` | None |
| Report drafter | Writes the report's text from approved results, one paragraph per call. It does not answer questions; people explore through the report's dashboard and disclosure groups | Approved metrics, actions and assumptions; `framework_digest.md` for framework context | A numbered draft in the report table, with metric and insight tokens | Metric lookup; search over the framework digest |
| Action proposer | Turns the drivers of each crop's loss into candidate actions, written as action specs | Loss drivers per crop and region, the action catalogue, the package's lever list | `action_definition` rows with status proposed | Catalogue search; read-only access to risk results |

Guardrails, enforced in code rather than in the prompt:

1. Every agent output is checked against its JSON schema and the prose check before it is stored. A failure goes back to the model with the error, at most twice. After that the call is recorded as failed and shows in its queue.
2. Evidence names the record keys and the query that produced it. The runner re-runs the query, and a proposal whose evidence does not reproduce is rejected automatically.
3. A rule proposed by an agent goes to review with its backtest attached: how many labelled issues it catches and how many correct records it flags. Its code runs only after a person approves it, and only in the sandbox service.
4. The explainer never types a number. It writes evidence tokens such as `{{ev:ratio_to_median}}`, which the app fills from the proposal's evidence values. A token that names no value fails the check.
5. The drafter never types a number either. It writes metric and insight tokens such as `{{metric:met_01JC...}}` and `{{insight:ins_01JC...}}`, which the app fills. A draft with any other figure, apart from years and scenario names, fails the check.
6. One call writes one paragraph or one explanation. Each call is logged in `llm_call` with the model, prompt version and input and output hashes, so every paragraph points to the call that wrote it. The published report's method section lists the models and prompt versions used. Screens label agent text "Suggested by the assistant" without naming the model.
7. If the Gemini key fails or its quota runs out, the wrapper switches to the fake model the tests use, and the call log records the switch.

## App screens

Six screens cover the demo. The two review screens and the risk view matter most; the others can stay plain.

| Screen | Who uses it | What it shows | What they can do |
| --- | --- | --- | --- |
| Runs | Data specialist | Each run with its recipe version, status and step timeline; inputs and outputs per step | Start a run; open any artifact |
| Data review | Data specialist | Proposals filtered by rule, table and status. Detail view: the record, old and new value, evidence with linked rows, the explainer's text | Approve, edit or reject with a comment; approve a whole rule's batch (logged as one decision per item) |
| Rule proposals | Data specialist | Rules the agent suggested, with their code and backtest on the labelled history; approved code runs only in the sandbox | Approve or reject |
| Risk view | Sustainability specialist, sourcing | Cost per year and in a 1-in-10 bad year by crop, region and scenario; chance of a bad year; extra emissions from replacement imports | Open any number to see its contributing farms, parcels, weather cells and raw rows, with the corrections applied to them; view and change assumptions, which starts a new run |
| Actions | Sustainability specialist, sourcing | Options with cost, risk removed and emissions change, and the assumptions behind each | Approve which proposed actions to run; mark results recommended, considered or rejected, with a comment |
| Report | Sustainability specialist, management | An interactive page: the drafted text, a dashboard of its key metrics and insights, and every number opening a disclosure group with its lineage (tables, filter in plain words, contributing rows, corrections and assumptions) | Approve and publish; redraft; export as Markdown, or as PDF through the browser's print with every disclosure group open |

## Work split

Five workstreams, one person each, build in parallel against four interfaces: the table schemas, the proposal columns and the step contract (all under Data model), and the API contract in docs/openapi.json. All four now exist in the repo; change them only through their owner.

| Workstream | Builds | Suggested owner | Needs from others | Done when |
| --- | --- | --- | --- | --- |
| Core and lineage | FastAPI backend and API contract, Postgres schema and migrations, the queue worker and runner, the SeaweedFS artifact store, the Docker Compose stack and the seed job, replay of raw plus approved proposals, what-if runs with action overrides; steps 1–6 refactored from the notebooks (milestone 1) | Strongest Python and data person | Nothing | A run of steps 1–6 shows in the Runs screen with every artifact registered |
| Risk module | Steps 7–10: yield model, scenario ensemble, pricing, actions | Whoever knows the notebooks best | Step contract; features from step 6 | Euros at risk per crop, region and scenario, with lineage, for all three scenarios |
| Data agents | Fix proposer, the sandbox service, review explainer with evidence tokens, the LLM wrapper with its retries, prose check and fake-model fallback; recipe 2 checks | LLM builder 1 | Proposal schema; raw artifacts | Agent proposals appear in the Data review queue with reproducible evidence |
| Report agent and app | Report drafter, action proposer, citation tokens; the six screens as a React web app, with the interactive report page, built against mock API data until the backend is ready | LLM builder 2 | Metric and decision tables | Approving a report publishes it, with every number linked |
| Recipe 2, docs and demo | Energy-meter recipe, the Vultr VM with Caddy and the shared password, README with usage instructions, method note, Fabric mapping, demo script and recording | Fifth person | Runner from core | A new person can run the demo from the README alone, and the app runs on the VM |

Order of milestones, each a gate for the next:

1. Skeleton: steps 1–6 run through the runner and land in the schema.
2. Numbers: steps 7–9 produce risk in euros for every crop, region and scenario.
3. Review loop: a proposal approved in the app changes the cleaned tables on the next run.
4. Actions and report: step 10 and the report run work end to end, and a published report links every number.
5. Freeze: a recorded demo run and finished docs. No new features after this point.

## Deliverables and demo

The brief asks for a working AI solution and documentation with usage instructions. We hand in five things:

- [ ] The repo, with a README that sets up and runs the platform from the unzipped package
- [ ] The running app on a Vultr VM behind a shared password, seeded with one complete run of each recipe
- [ ] A one-page method note: data sources, assumptions, limits, and how review and approval work
- [ ] A Fabric mapping: raw, cleaned and result layers as Lakehouse tables; agents in Azure AI Foundry; the web app on Azure App Service with Entra ID sign-in
- [ ] A recorded demo of about five minutes, plus slides

Demo script:

1. The problem, in one slide: Apetit's climate data is scattered, and farming risk is priced nowhere.
2. Start a run of recipe 1 from the raw package and show its steps completing.
3. Data review: open an agent proposal, read its evidence and explanation, approve it. Reject another and say why.
4. Risk view: cost per year for each crop and region under the three climate scenarios. Click one figure and follow it down to farms, weather cells and the raw survey rows, including the correction just approved.
5. Actions: compare irrigation, relocation, earlier sowing and heat-tolerant pea on cost and risk removed, and show the Foodhills supply insight.
6. Report: open the interactive report, expand a number to its lineage, approve it and publish.
7. The path to production: the same layers on Fabric, and the next recipes (GHG inventory, SBTi pathways, nature impacts in lake catchments) on the same base.

## Open questions

Two are still open: the submission deadline and who plays the reviewer. Decisions made along the way are recorded in the sections they affect.

| Question | Recommendation | Why it matters |
| --- | --- | --- |
| When exactly is the submission deadline, and is the demo live or recorded? | Check the event guide today | Sets the freeze time |
| Who plays the reviewer in the demo? | One team member, named on screen as the approver | Shows that a named person signs off |
