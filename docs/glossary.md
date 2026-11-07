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
| Driver | `driver` | Driver | A weather cause of loss, such as heat at flowering or drought in the sensitive stage |
| Climate scenario | `scenario` (`historical`, `ssp126`, `ssp245`, `ssp585`) | Past weather, Low emissions (SSP1-2.6), Middle (SSP2-4.5), High emissions (SSP5-8.5) | The SSP weather a number uses |
| Transition scenario | `ngfs_scenario` | See Transition scenarios below | The NGFS scenario that sets import premiums |
| Crop calendar | `crop_params` | Crop calendar | Sowing trigger, maturity degree-days and sensitive window for a region and crop |
| Shortfall | `shortfall` | Shortfall | Contracted volume minus what the farms deliver in a season, when positive |
| Contracted volume | `contracted_volume` | Contracted volume | 2025 contract area times today's normal yield |
| Bad year | `bad_year` | Bad year | A season with yield under 80% of the 1991–2020 average |
| Replacement premium | `replacement_premium` | Replacement premium | Extra cost per tonne of buying a shortfall on the market |
| Lever | `lever`, `lever_id` | Lever | One row of the package's lever list, `decarbonisation_levers.csv` |

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
| Decision | `decision` | Decision | One person's approve, edit or reject, never changed afterwards |
| Result set | `result_set` | Results | All results of one run, reviewed and published together |
| Metric | `metric` | (the number itself) | One result number with its lineage |
| Lineage | `lineage` | Sources | The tables and filter that select the rows behind a metric |
| Assumption | `assumption` | Assumption | An input value a person can question and change |
| Action | `action_definition` | Action | A catalogue or agent-proposed spec with one typed override, priced as a what-if |
| Action option | `action_option` | Action option | An action's priced what-if result: cost, risk reduced and emissions change |
| What-if run | `kind = "what_if"` | What-if | A run that starts from an approved run with one action applied |
| Insight | `insight` | Insight | A finding that is not a priced metric, with numbers only as metric tokens |
| Catalogue policy | `reviewer = "Catalogue policy"` | Approved by catalogue policy | Approval of the seeded catalogue actions, so the first run has actions to price |

## Transition scenarios

The package's NGFS scenarios, the name to show for each, and the climate scenario each is matched to (the `physical_pathway_proxy` column of `transition_scenarios.csv`):

| In code | In the app | Climate scenario |
| --- | --- | --- |
| `net_zero_2050` | Net Zero 2050 | Low emissions (SSP1-2.6) |
| `below_2c` | Below 2°C | Low emissions (SSP1-2.6) |
| `low_demand` | Low Demand | Low emissions (SSP1-2.6) |
| `delayed_transition` | Delayed Transition | Middle (SSP2-4.5) |
| `fragmented_world` | Fragmented World | Middle (SSP2-4.5) |
| `ndcs` | Nationally Determined Contributions (NDCs) | Middle (SSP2-4.5) |
| `current_policies` | Current Policies | High emissions (SSP5-8.5) |

"Scenario" alone is never used in app copy or reports. Say "climate scenario" or "transition scenario".
