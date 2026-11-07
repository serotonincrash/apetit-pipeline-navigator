"""Write the API's OpenAPI document to docs/openapi.json, for generating the frontend client.

Run from backend/: uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from navigator.api.main import app
from navigator.logs import get_logger

TARGET = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"

log = get_logger(__name__)


def main() -> None:
    TARGET.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
    log.info("openapi written", extra={"path": str(TARGET), "paths": len(app.openapi()["paths"])})


if __name__ == "__main__":
    main()
