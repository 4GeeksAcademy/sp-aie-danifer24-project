"""Client adapter for requesting Prefect deployments of the business flow."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any


def _resolve_week_start(value: date | str | None) -> date:
    if value is None:
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7)
    resolved = date.fromisoformat(value) if isinstance(value, str) else value
    if resolved.weekday() != 0:
        raise ValueError("week_start must be an ISO week Monday")
    return resolved


def start_weekly_office_program_performance(
    week_start: date | str | None = None,
) -> dict[str, Any]:
    """Create a Prefect deployment run; never execute ETL in the API process."""
    resolved_week = _resolve_week_start(week_start)
    deployment_name = os.getenv(
        "BUSINESS_PERFORMANCE_DEPLOYMENT", "weekly-office-program-performance/weekly"
    )
    from prefect.deployments import run_deployment

    flow_run = run_deployment(
        deployment_name,
        parameters={"week_start": resolved_week.isoformat()},
        timeout=0,
        as_subflow=False,
    )
    flow_run_id = str(flow_run.id)
    return {
        "run_id": flow_run_id,
        "flow_run_id": flow_run_id,
        "status": "Running",
        "week_start": resolved_week,
    }
