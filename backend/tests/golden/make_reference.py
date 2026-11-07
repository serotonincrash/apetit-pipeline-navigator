"""Write the golden reference fingerprints from the notebooks' outputs.

Run the notebooks first (notebooks/README.md), then:

    uv run python -m tests.golden.make_reference ../notebooks/outputs

The fingerprints are committed; rerun this only when a notebook's results change on purpose.
"""

import sys
from pathlib import Path

import pandas as pd

from tests.golden.fingerprint import save

TABLES = {
    "corrections_log": "corrections_log.csv",
    "rule_validation": "rule_validation.csv",
    "farm_survey_clean": "farm_survey_fi_clean.csv",
    "foodhills_clean": "foodhills_se_clean.csv",
    "farm_registry_clean": "farm_registry_clean.csv",
    "parcel_features": "parcel_features.csv",
    "parcel_year_contract": "parcel_year_contract.csv",
    "training_table": "c1_training_table.csv",
    "calendar_tuning": "calendar_tuning.csv",
    "weather_features_cell": "weather_features_cell.parquet",
    "parcel_year_features": "c1_parcel_year_features.parquet",
    "model_table": "c1_model_table.csv",
}


def main(outputs: Path) -> None:
    for name, file in TABLES.items():
        path = outputs / file
        frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        save(name, frame)
        print(f"{name:24s} {frame.shape}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
