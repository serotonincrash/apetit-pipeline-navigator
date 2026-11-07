"""Recipe 2: energy-meter check, from raw meter readings to Scope 2 for electricity.

Each step names the tables it reads. A name is either a table an earlier step returned, or
`proposals`, which the runner fills with this run's proposals and their current status.
"""

from navigator.recipes.core import PROPOSALS_INPUT, Recipe, StepSpec

# Grid average factors, t CO2e per MWh (the package gives kg per kWh, which is the same number).
# Years are text because run overrides come back from JSON.
LOCATION_T_PER_MWH = {
    "FI": {
        "2019": 0.090,
        "2020": 0.068,
        "2021": 0.075,
        "2022": 0.066,
        "2023": 0.038,
        "2024": 0.030,
        "2025": 0.026,
    },
    "SE": {str(year): 0.012 for year in range(2019, 2026)},
}
# Residual mix, t CO2e per MWh, for electricity no guarantee of origin covers.
RESIDUAL_T_PER_MWH = {
    "FI": {
        "2019": 0.354,
        "2020": 0.370,
        "2021": 0.380,
        "2022": 0.390,
        "2023": 0.400,
        "2024": 0.406,
        "2025": 0.406,
    },
    "SE": {
        "2019": 0.040,
        "2020": 0.045,
        "2021": 0.040,
        "2022": 0.040,
        "2023": 0.038,
        "2024": 0.036,
        "2025": 0.035,
    },
}

RAW_FILES = {
    "energy_meter_readings": {"path": "data/02_raw_feeds/energy_meter_readings.csv"},
    "goo_registry_statement": {"path": "data/02_raw_feeds/goo_registry_statement.csv"},
    "sites": {"path": "data/01_master/sites.csv"},
    "dev_issue_labels": {"path": "tasks/dev/A1_dev_issue_labels_2023_2024.csv"},
    "a2_inventory_2023": {"path": "tasks/dev/A2_dev_inventory_2023.csv"},
    "a2_inventory_2024": {"path": "tasks/dev/A2_dev_inventory_2024.csv"},
}

# How close a fixed reading must be to the labelled true reading to count as a match.
VALUE_TOLERANCE = 0.1

RECIPE = Recipe(
    recipe_id="energy_meter_check",
    version=1,
    title="Energy-meter check",
    steps=(
        StepSpec("load_raw", inputs=(), params={"files": RAW_FILES}),
        StepSpec(
            "check_meters",
            inputs=("energy_meter_readings", "dev_issue_labels"),
            params={
                # Set on the 2023-24 labels: the lowest labelled unit error is about 1,000 times
                # the meter's median, and the highest correct reading is far below 100 times.
                "unit_error_min_ratio_to_meter_median": 100.0,
                "kwh_per_mwh": 1000.0,
                # Set on the 2023-24 labels: the lowest labelled spike is 3.0 times the same
                # month in other years, and the highest correct reading is 2.2 times.
                "spike_min_ratio_to_same_month": 2.5,
                "backtest_value_tolerance": VALUE_TOLERANCE,
            },
        ),
        StepSpec(
            "propose_fixes",
            inputs=(
                "energy_meter_readings",
                "dev_issue_labels",
                "rule_validation",
                PROPOSALS_INPUT,
            ),
            params={
                # The run request switches this on; see `run_fix_proposer` in POST /api/runs.
                "enabled": False,
                "tables": ["energy_meter_readings"],
                "concurrency": 1,
            },
        ),
        StepSpec(
            "explain_proposals",
            inputs=(PROPOSALS_INPUT,),
            params={"max_explanations": None, "concurrency": 8},
        ),
        StepSpec(
            "backtest_meters",
            inputs=("dev_issue_labels", PROPOSALS_INPUT),
            params={"value_tolerance": VALUE_TOLERANCE},
        ),
        StepSpec(
            "apply_approved_meters",
            inputs=("energy_meter_readings", PROPOSALS_INPUT),
        ),
        StepSpec(
            "scope2_electricity",
            inputs=("energy_clean", "sites", "goo_registry_statement"),
            params={
                "location_t_per_mwh": LOCATION_T_PER_MWH,
                "residual_t_per_mwh": RESIDUAL_T_PER_MWH,
            },
        ),
        StepSpec(
            "compare_inventory",
            inputs=("scope2_site_year", "a2_inventory_2023", "a2_inventory_2024"),
            params={
                "answer_tables": ["a2_inventory_2023", "a2_inventory_2024"],
                "answer_category": "purchased_electricity",
                "answer_scopes": {
                    "scope2_location": "location_based_tco2e",
                    "scope2_market": "market_based_tco2e",
                },
            },
        ),
    ),
)
