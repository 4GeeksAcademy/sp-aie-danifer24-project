"""Read-only queries for the published business reporting tables.

Kept under ``data.pipelines`` so API routes delegate storage logic rather than
embedding SQL or duplicating pipeline behavior.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _reporting_engine():
    """Create a reporting engine, reusing the API DB URL when not overridden."""
    value = os.getenv("REPORTING_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("REPORTING_DATABASE_URL or DATABASE_URL must be set")
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Reporting database connections must use PostgreSQL")
    return create_engine(
        url.set(drivername="postgresql+psycopg2"), pool_pre_ping=True
    )


def _resolve_week_start(value: date | str | None) -> date:
    """Resolve most recently completed week or validate an ISO Monday."""
    if value is None:
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7)
    resolved = date.fromisoformat(value) if isinstance(value, str) else value
    if resolved.weekday() != 0:
        raise ValueError("week_start must be an ISO week Monday")
    return resolved



def get_latest_pipeline_run() -> dict[str, Any] | None:
    """Return the latest audit row, ordered by start time then run ID."""
    engine = _reporting_engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """SELECT run_id, flow_name, status, week_start, started_at,
                              ended_at, processed_records, accepted_records,
                              rejected_records, rows_written, error_code, error_message
                       FROM reporting.pipeline_runs
                       ORDER BY started_at DESC, run_id DESC
                       LIMIT 1"""
                )
            ).mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        engine.dispose()


def get_weekly_office_program_performance(
    week_start: date | str | None = None,
) -> dict[str, Any]:
    """Read KPI rows for one week, defaulting to the most recently completed week."""
    engine = _reporting_engine()
    try:
        with engine.connect() as connection:
            if week_start is None:
                published_week = connection.execute(
                    text(
                        "SELECT MAX(week_start) "
                        "FROM reporting.weekly_office_program_performance"
                    )
                ).scalar_one_or_none()
                resolved_week = published_week or _resolve_week_start(None)
            else:
                resolved_week = _resolve_week_start(week_start)
            rows = connection.execute(
                text(
                    """SELECT office, programme_id, week_start, total_material_cost,
                              kits_delivered_count, shortage_events_count,
                              cost_variance_events_count, currency
                       FROM reporting.weekly_office_program_performance
                       WHERE week_start = :week_start
                       ORDER BY office, programme_id"""
                ),
                {"week_start": resolved_week},
            ).mappings().all()
            return {
                "week_start": resolved_week,
                "entries": [dict(row) for row in rows],
            }
    finally:
        engine.dispose()
