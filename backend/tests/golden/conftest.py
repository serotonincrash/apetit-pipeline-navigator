"""Shared fixtures for golden tests: the challenge package read from disk, as the runner would
serve it from object storage."""

import hashlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from navigator.recipes.core import RunContext, SourceFile


class DiskPackage(Mapping[str, SourceFile]):
    def __init__(self, root: Path) -> None:
        self.root = root

    def __getitem__(self, path: str) -> SourceFile:
        content = (self.root / path).read_bytes()
        return SourceFile(path=path, sha256=hashlib.sha256(content).hexdigest(), content=content)

    def __iter__(self) -> Iterator[str]:
        return (str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())

    def __len__(self) -> int:
        return sum(1 for _ in self)


@pytest.fixture(scope="session")
def package_root() -> Path:
    root = Path(os.environ.get("PACKAGE_DIR", "../APETIT_CLIMATE_NATURE_NAVIGATOR_2026")).resolve()
    if not (root / "data").exists():
        pytest.skip(f"challenge package not found at {root}; set PACKAGE_DIR")
    return root


@pytest.fixture(scope="session")
def ctx(package_root: Path) -> RunContext:
    return RunContext(
        run_id="run_golden", recipe_id="farm_climate_risk", sources=DiskPackage(package_root)
    )
