"""Risk view: result sets, their metrics, where each number came from, and the assumptions."""

from typing import Annotated

from fastapi import APIRouter, Query

from navigator.api import schemas
from navigator.api.errors import NOT_BUILT, NOT_FOUND, not_built

router = APIRouter(prefix="/api", tags=["risk"])

MILESTONE_2 = "come in milestone 2, with the risk numbers."


@router.get("/result-sets", operation_id="listResultSets", responses=NOT_BUILT)
def list_result_sets(
    run_id: str | None = None,
    result_set_status: Annotated[schemas.ResultSetStatus | None, Query(alias="status")] = None,
) -> list[schemas.ResultSet]:
    """Result sets, newest first, optionally those of one run."""
    raise not_built(f"Result sets {MILESTONE_2}")


@router.get(
    "/result-sets/{result_set_id}/metrics",
    operation_id="listMetrics",
    responses={**NOT_FOUND, **NOT_BUILT},
)
def list_metrics(
    result_set_id: str,
    name: str | None = None,
    region: str | None = None,
    crop: str | None = None,
    scenario: str | None = None,
    ngfs_scenario: str | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> schemas.MetricList:
    """Metrics of a result set, filtered by region, crop, climate and NGFS scenario."""
    raise not_built(f"Metrics {MILESTONE_2}")


@router.get(
    "/metrics/{metric_id}/sources",
    operation_id="getMetricSources",
    responses={**NOT_FOUND, **NOT_BUILT},
)
def get_metric_sources(metric_id: str) -> schemas.MetricSources:
    """Where a number came from: source tables and filters, corrections and assumptions."""
    raise not_built(f"Metric sources {MILESTONE_2}")


@router.get("/assumptions", operation_id="listAssumptions", responses=NOT_BUILT)
def list_assumptions(
    result_set_id: str | None = None, run_id: str | None = None
) -> list[schemas.Assumption]:
    """Assumptions behind a result set or run. Changing one means queuing a run with overrides."""
    raise not_built(f"Assumptions {MILESTONE_2}")
