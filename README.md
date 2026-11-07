# Apetit Climate & Nature Navigator: Track C notebooks

Notebooks for Track C (climate risk to farming) of the Since AI Hackathon 2026. They read the unzipped challenge package and never change it.

## Setup

The notebooks expect the package at `../APETIT_CLIMATE_NATURE_NAVIGATOR_2026`. If it's somewhere else, set `CCN_PKG` to its path.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Run the notebooks in this order. Open each one and choose Run All, or run them from the command line:

```bash
python run_notebook.py c1_clean.ipynb
python run_notebook.py c1_weather_features.ipynb   # about 30 seconds
python run_notebook.py c1_experiments.ipynb        # about 25 seconds
python run_notebook.py c1_yield_model.ipynb        # about 10 seconds
python run_notebook.py c2_yield_projection.ipynb   # about 10 seconds
python run_notebook.py c3_risk_pricing.ipynb       # about 10 seconds
python run_notebook.py c4_actions.ipynb            # about 10 seconds
```

## Notebooks

| Notebook | What it does | Main outputs |
|---|---|---|
| `c1_clean.ipynb` | Fixes errors in the farm yield history, matches parcels to weather cells and builds the training table | `outputs/c1_training_table.csv`, `outputs/parcel_year_contract.csv`, `outputs/corrections_log.csv` |
| `c1_weather_features.ipynb` | Works out crop stress from daily weather and tunes the crop calendar for each region and crop | `outputs/c1_model_table.csv` (training), `outputs/c1_parcel_year_features.parquet` (C1 predictions), `outputs/weather_features_cell.parquet` (all climate scenarios, for C2), `results/` (tuning record) |
| `c1_experiments.ipynb` | Records the experiments behind the weather-feature design and what each one changed | Results stay in the notebook |
| `c1_yield_model.ipynb` | Fits the yield model for each region and crop, tests it on unseen seasons and predicts every planned parcel for 2027–31 | `outputs/c1_yield_predictions_2027_2031.csv` (C1 template filled in), `outputs/yield_model.json`, `results/yield_backtest.png` and summary |
| `c2_yield_projection.ipynb` | Projects 2041–60 yields and the chance of a bad year under ssp126, ssp245 and ssp585, by shifting the 1991–2020 seasons to each scenario's climate | `outputs/yield_projection_draws.parquet` (input to the risk pricing), `outputs/c2_climate_yield_risk.csv` (C2 template filled in), `results/yield_projection_2041_2060.csv` and chart |
| `c3_risk_pricing.ipynb` | Prices 2041–60 shortfalls as market imports: expected and 1-in-10 extra cost in euros, and the emissions of replacement imports, per crop, climate scenario and paired NGFS scenario; reports the Foodhills cover as an insight | `outputs/climate_risk_priced.parquet` (input to comparing actions), `results/climate_risk_eur.csv`, `results/climate_risk_total.csv`, `results/risk_assumptions.csv` and chart |
| `c4_actions.ipynb` | Breaks each crop's loss into weather drivers, then runs each action in `actions/catalogue.json` as a what-if and prices what it removes; refuses actions the model can't estimate | `results/action_options.csv`, `results/loss_drivers.csv`, `results/actions_not_run.csv` and chart |

The shared code is in `cropweather.py` (crop calendar, soil water, stress measures), `yieldcv.py` (cross-validation and model inputs) `yieldmodel.py` (fitting and predicting), `climateproj.py` (shifted seasons and simulation), `riskprice.py` (shortfalls in euros and emissions) and `actions.py` (action specs and what-if overrides). Action specs live in `actions/catalogue.json`, so C1 and C2 use the same definitions.

`outputs/` is rebuilt on every run and isn't tracked in git. `results/` is small and is tracked. It holds the full tuning record (`calendar_tuning.csv`), the chosen settings (`calendar_choice.csv`), the crop parameters (`crop_params.json`), the yield model's coefficients and error estimates (`yield_model.json`) and its backtest (`yield_backtest.csv`, `yield_backtest_summary.csv` and two charts).

## Cleaning rules

| Rule | Problem | Fix | Result on the 2023–24 answer key |
|---|---|---|---|
| R1 | Yield typed 10 times too large | Divide by 10 | Caught 2 of 2, no false alarms |
| R2 | Nitrogen rate with a misplaced decimal point | Multiply or divide by 10 | Caught 6 of 6, no false alarms |
| R3 | Survey area doesn't match the farm's parcels | Use the parcel total | Caught 18 of 18, no false alarms |
| R4 | Organic soil reported as mineral | Flag for review only, because the soil map is about 88% accurate | Caught 23 of 33, 7 false alarms |
| R5 | Farm latitude and longitude swapped | Swap back | Not in the answer key; confirmed by parcel locations |

## Expert review

Every proposed fix is logged in `outputs/corrections_log.csv` with its evidence and who proposed and approved it. Fixes from rules with no false alarms on the answer key are approved automatically. Everything else waits for a person.

To approve or reject one fix, add a row to `review/decisions.csv`:

```
correction_id,decision,reviewer,comment,decided_at
R4|farm_survey:FS00200|soil_type_reported,approve,A. Reviewer,parcel register confirms peat,2026-11-07
```

`decision` is `approve` or `reject`. Run the notebook again, and only approved fixes reach the cleaned tables.

The data is synthetic. Don't present results as facts about Apetit or real farms.
