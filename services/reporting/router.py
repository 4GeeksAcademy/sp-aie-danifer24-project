"""Authenticated HTTP adapter for the weekly business reporting pipeline."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data.pipelines.reporting_store import (
    get_latest_pipeline_run,
    get_weekly_office_program_performance,
)
from services.api.security import get_current_user
from services.tasks import start_weekly_pipeline
from services.reporting.schemas import (
    PipelineRunResponse,
    StartPipelineRunResponse,
    StartPipelineRunRequest,
    WeeklyKPIResponse,
)


router = APIRouter(
    prefix="/reporting",
    tags=["reporting"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/pipeline-runs/latest", response_model=PipelineRunResponse)
def latest_pipeline_run():
    """Return the newest pipeline run and its audit metadata."""
    run = get_latest_pipeline_run()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aún no hay corridas registradas del pipeline.",
        )
    return {**run, "flow_run_id": run["run_id"]}


@router.post(
    "/pipeline-runs",
    response_model=StartPipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_pipeline_run(request: StartPipelineRunRequest | None = None):
    """Queue the reporting ETL for execution by the Celery worker."""
    week_start: date | None = request.week_start if request is not None else None
    if week_start is not None and week_start.weekday() != 0:
        raise HTTPException(status_code=422, detail="week_start must be an ISO week Monday")
    try:
        queued_task = start_weekly_pipeline.delay(
            week_start.isoformat() if week_start is not None else None
        )
        return {"task_id": queued_task.id}
    except Exception as error:
        # Avoid leaking broker connection details through the API response.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo encolar el pipeline.",
        ) from error


@router.get(
    "/weekly-office-program-performance",
    response_model=WeeklyKPIResponse,
)
def weekly_office_program_performance(
    week_start: date | None = Query(default=None),
):
    """Return published KPI rows for a selected (or latest completed) week."""
    try:
        return get_weekly_office_program_performance(week_start)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
