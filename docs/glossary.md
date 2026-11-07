# Glossary

One term for one thing, in code, annotations, agent text and the app. The "In the app" column
is what people see; the "In code" column is the name in tables, columns and functions.

## Farming and climate

| Term | In code | In the app | Meaning |
| --- | --- | --- | --- |
| Farm | `farm`, `farm_id` | Farm | A contract grower, in the farm registry |
| Parcel | `parcel`, `parcel_id` | Parcel | One field of a farm, with its soil and location |
| Season | `season`, `year` | Season | One growing year, 1 March to 31 October |
| Farm-year | `farm_year` | Farm and season | One farm's results for one crop in one season |
| Region | `region` (`FI_SW`, `SE_SKANE`) | South-west Finland, Skåne | The two growing regions |
| Crop | `crop` (`pea`, `turnip_rape`, `potato`, `carrot`, `spinach`) | Pea, Turnip rape, Potato, Carrot, Spinach | The five contract crops |
| Weather cell | `cell`, `cell_id` | Weather cell | One square of the weather grid |
| Climate scenario | `scenario` (`historical`, `ssp126`, `ssp245`, `ssp585`) | Past weather, Low emissions (SSP1-2.6), Middle (SSP2-4.5), High emissions (SSP5-8.5) | Which weather a number uses |
| NGFS scenario | `ngfs_scenario` | As named by NGFS | The transition scenario that sets import premiums |
| Crop calendar | `crop_params` | Crop calendar | Sowing trigger, maturity degree-days and sensitive window for a region and crop |
| Shortfall | `shortfall` | Shortfall | Contracted volume minus what the farms deliver in a season, when positive |
| Contracted volume | `contracted_volume` | Contracted volume | 2025 contract area times today's normal yield |
| Bad year | `bad_year` | Bad year | A season with yield under 80% of the 1991–2020 average |
| Replacement premium | `replacement_premium` | Replacement premium | Extra cost per tonne of buying a shortfall on the market |

## Platform

| Term | In code | In the app | Meaning |
| --- | --- | --- | --- |
| Recipe | `recipe` | Recipe | An ordered list of steps that turns raw files into results |
| Run | `run` | Run | One execution of a recipe |
| Step | `step`, `step_run` | Step | One part of a recipe, such as checking farm data |
| Section | `section` | Part of a step | A named block inside a step, reported live |
| Artifact | `artifact` | Table | A table a step wrote, stored as Parquet |
| Proposal | `proposal` | Suggested fix, Flag | A suggested change to one field of one record, or a flag on it |
| Fix | `action = "fix"` | Fix | A proposal that changes a value once approved |
| Flag | `action = "flag"` | Flag | A proposal that marks a record without changing it |
| Rule | `rule` | Data check | A written check that produces proposals |
| Rule policy | `reviewer = "Rule policy"` | Approved by data check policy | Approval of a rule's fixes because its backtest was perfect |
| Decision | `decision` | Decision | One person's approve, edit or reject, never changed afterwards |
| Result set | `result_set` | Results | All results of one run, reviewed and published together |
| Metric | `metric` | (the number itself) | One result number with its lineage |
| Lineage | `lineage` | Sources | The tables and filter that select the rows behind a metric |
| Assumption | `assumption` | Assumption | An input value a person can question and change |
| Action | `action_definition` | Action | An override on the model's inputs that is priced as a what-if |
| What-if run | `kind = "what_if"` | What-if | A run that starts from an approved run with one action applied |
