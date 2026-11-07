"""Recipe 1: farm climate risk, steps 1 to 9.

Each step names the tables it reads. A name is either a table an earlier step returned or
`proposals`, which the runner fills with this run's proposals and their current status.
"""

from navigator.recipes.core import PROPOSALS_INPUT, Recipe, StepSpec

CONTRACT_CROPS = ["pea", "turnip_rape", "potato", "carrot", "spinach"]

# The region and crop pairs the weather, yield and pricing steps work on.
UNITS = [
    ["FI_SW", "pea"],
    ["SE_SKANE", "pea"],
    ["FI_SW", "turnip_rape"],
    ["FI_SW", "potato"],
    ["FI_SW", "carrot"],
    ["FI_SW", "spinach"],
]
REGION_CELL_PREFIX = {"FI_SW": "GF", "SE_SKANE": "GS"}

# Import emission factors, t CO2e per t.
IMPORT_EF = {
    "FI_SW/pea": 0.488368,
    "SE_SKANE/pea": 0.488368,
    "FI_SW/potato": 0.328368,
    "FI_SW/carrot": 0.308368,
    "FI_SW/spinach": 0.358368,
    "FI_SW/turnip_rape": 1.352459,
}

# Each raw table: its path in the package and how to read it.
RAW_FILES = {
    "farm_survey": {"path": "data/03_farming/farm_survey_fi.csv"},
    "foodhills": {
        "path": "data/03_farming/foodhills_odlingsdata_se.csv",
        "read": {"sep": ";", "decimal": ","},
    },
    "farm_registry": {"path": "data/01_master/farm_registry.csv"},
    "parcels": {"path": "data/01_master/parcels.csv"},
    "crop_history": {"path": "data/03_farming/parcel_crop_history_and_plan.csv"},
    "grid": {"path": "data/01_master/climate_grid_cells.csv"},
    "erp_purchase_lines": {"path": "data/02_raw_feeds/erp_purchase_lines_2021_2025.csv"},
    "weather_daily": {"path": "data/04_climate/weather_daily_1991_2060.parquet"},
    "dev_issue_labels": {"path": "tasks/dev/A1_dev_issue_labels_2023_2024.csv"},
    "c1_template": {"path": "tasks/templates/C1_yields_2027_2031_submission.csv"},
    "climate_change_signals": {"path": "data/04_climate/climate_change_signals.csv"},
    "contract_prices": {"path": "data/05_scenarios/contract_prices_and_replacement_premiums.csv"},
    "transition_scenarios": {"path": "data/05_scenarios/transition_scenarios.csv"},
}

RECIPE = Recipe(
    recipe_id="farm_climate_risk",
    version=2,
    title="Farm climate risk",
    steps=(
        StepSpec("load_raw", inputs=(), params={"files": RAW_FILES}),
        StepSpec(
            "check_farm_data",
            inputs=(
                "farm_survey",
                "farm_registry",
                "parcels",
                "crop_history",
                "dev_issue_labels",
            ),
            params={
                "r1_yield_max_ratio_to_median": 5.0,
                "r2_nitrogen_ratio_high": 5.0,
                "r2_nitrogen_ratio_low": 0.2,
                "r3_area_tolerance": 0.01,
                "r4_organic_share_threshold": 0.30,
                # How close a fixed value must be to the answer key's true value to count as a
                # match in the backtest.
                "backtest_value_tolerance": {"relative": 0.01, "absolute": 0.11},
            },
        ),
        StepSpec(
            "apply_approved",
            inputs=(
                "farm_survey",
                "foodhills",
                "farm_registry",
                "parcels",
                "crop_history",
                PROPOSALS_INPUT,
            ),
            params={"r3_area_tolerance": 0.01},
        ),
        StepSpec(
            "spatial_join",
            inputs=(
                "parcels",
                "grid",
                "crop_history",
                "farm_registry_clean",
                "farm_survey_clean",
                "foodhills_clean",
                "c1_template",
                PROPOSALS_INPUT,
            ),
            params={
                "contract_crops": CONTRACT_CROPS,
                "max_cell_distance_km": 20.0,
                "max_farm_to_parcels_km": 10.0,
                "template_area_tolerance_ha": 0.01,
                "max_yield_ratio_to_median": 5.0,
            },
        ),
        StepSpec(
            "tune_calendar",
            inputs=(
                "weather_daily",
                "training_table",
                "parcel_year_contract",
                "erp_purchase_lines",
            ),
            params={
                "units": UNITS,
                "region_cell_prefix": REGION_CELL_PREFIX,
                "gdd_maturity_grid": {
                    "pea": [500, 1200, 100],
                    "turnip_rape": [900, 1500, 100],
                    "potato": [900, 1700, 100],
                    "carrot": [700, 1700, 100],
                    "spinach": [300, 750, 50],
                },
                "window_start_grid": [0.20, 0.35, 0.50, 0.65],
                "window_span_grid": [0.30, 0.50],
                "sowing_temp_grid": [6, 9],
                "delivery_materials": {
                    "M110": "pea",
                    "M100": "turnip_rape",
                    "M111": "potato",
                    "M112": "carrot",
                    "M113": "spinach",
                },
                "ready_window_lead_days": 21,
                "delivery_quantiles": [0.05, 0.95],
                "flower_window_share": 0.25,
                "error_tolerance": 0.05,
                "weak_identification_farm_years": 300,
            },
        ),
        StepSpec(
            "weather_features",
            inputs=(
                "weather_daily",
                "crop_params",
                "training_table",
                "parcel_year_contract",
                "c1_template",
            ),
            params={
                "c1_scenario": "ssp245",
                "region_cell_prefix": REGION_CELL_PREFIX,
            },
        ),
        StepSpec(
            "fit_yield_model",
            inputs=("model_table",),
            params={"units": UNITS, "ridge_strength": 0.01, "shrink_seasons": 2.0},
        ),
        StepSpec(
            "project_yields",
            inputs=(
                "yield_coefficients",
                "yield_fit",
                "farm_levels",
                "model_table",
                "parcel_year_features",
                "crop_params",
                "weather_daily",
                "climate_change_signals",
            ),
            params={
                "units": UNITS,
                "region_cell_prefix": REGION_CELL_PREFIX,
                # Contract parcels are the ones declared for this season.
                "contract_year": 2025,
                "trend_year": 2026,
                "simulated_outcomes": 50,
                "simulation_seed": 2026,
                "bootstrap_samples": 300,
                "bootstrap_seed": 7,
                "bad_year_share": 0.8,
            },
        ),
        StepSpec(
            "price_risk",
            inputs=("yield_draws", "contract_prices", "transition_scenarios"),
            params={
                # Tonnes of CO2e per tonne imported, by region and crop. Copied from
                # notebooks/results/import_ef.json, built in section 1 of c3_risk_pricing.ipynb.
                "import_ef": IMPORT_EF,
                "price_year": 2025,
                "premium_years": [2045, 2050],
                # Replaces values of the price file, by its item and then its column.
                "price_overrides": {},
                # Replaces the computed premium rise of a transition scenario, as a fraction.
                "replacement_premium_lift": {},
                "foodhills_short_share": 0.1,
            },
        ),
    ),
)
