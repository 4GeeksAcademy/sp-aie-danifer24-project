"""Prefect flow for weekly office/program business performance reporting.

Run locally with ``uv run python -m data.pipelines.pipeline [YYYY-MM-DD]``.
The source database is read-only for this pipeline; reporting writes are kept in
the separate reporting schema.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.context import get_run_context
from prefect.states import State
from prefect.tasks import task_input_hash
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from data.process.business_performance import validate_and_aggregate


EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "kit_cost_variance_detected",
)


def _database_url(variable: str) -> URL:
    value = os.getenv(variable)
    if not value:
        raise RuntimeError(f"{variable} must be set")
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Pipeline database connections must use PostgreSQL")
    return url.set(drivername="postgresql+psycopg2")


def _resolve_week_start(value: date | str | None) -> date:
    if value is None:
        today = datetime.now(timezone.utc).date()
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7)
    resolved = date.fromisoformat(value) if isinstance(value, str) else value
    if resolved.weekday() != 0:
        raise ValueError("week_start must be an ISO week Monday")
    return resolved


@task(name="resolve-week", retries=0)
def resolve_week(week_start: date | str | None = None) -> date:
    """Resolve an explicit Monday, or the most recently completed ISO week."""
    return _resolve_week_start(week_start)


# One retry after one second handles a transient reporting DB connection failure
# without adding a long delay before any business data has been processed.
@task(name="start-pipeline-run", retries=1, retry_delay_seconds=1)
def start_pipeline_run(week_start: date, run_id: str) -> str:
    """Create an idempotent audit row linked to this Prefect flow run."""
    reporting_url = _database_url("REPORTING_DATABASE_URL")
    engine = create_engine(reporting_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO reporting.pipeline_runs
                       (run_id, flow_name, status, week_start, started_at)
                       VALUES (:run_id, 'weekly_office_program_performance', 'Running', :week_start, now())
                       ON CONFLICT (run_id) DO NOTHING"""
                ),
                {"run_id": run_id, "week_start": week_start},
            )
            audit_row = connection.execute(
                text("SELECT status, week_start FROM reporting.pipeline_runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).one_or_none()
            if audit_row is None or audit_row.week_start != week_start or audit_row.status != "Running":
                raise RuntimeError("Pipeline run audit row is inconsistent")
        return run_id
    finally:
        engine.dispose()


# Three retries with backoff cover brief source DB/network incidents and cap extra
# waiting at 21 seconds; this source operation is read-only and safe to repeat.
@task(name="extract-events", retries=3, retry_delay_seconds=[1, 5, 15])
def extract_events(week_start: date) -> list[dict[str, Any]]:
    """Read required business events from telemetry_events without mutations."""
    if os.getenv("TELEMETRY_DATABASE_READ_ONLY", "").lower() != "true":
        raise RuntimeError("TELEMETRY_DATABASE_READ_ONLY=true is required")
    source_url = _database_url("TELEMETRY_DATABASE_URL")
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    engine = create_engine(source_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT event_id, event_type, timestamp, tags
                       FROM public.telemetry_events
                       WHERE timestamp >= :start AND timestamp < :end
                         AND event_type = ANY(CAST(:event_types AS text[]))
                       ORDER BY timestamp, event_id"""
                ),
                {"start": start, "end": end, "event_types": list(EVENT_TYPES)},
            ).mappings()
            return [dict(row) for row in rows]
    finally:
        engine.dispose()


# task_input_hash fingerprints the complete records + week_start inputs, so only
# identical batches share a result; one hour bounds staleness while avoiding costly
# repeated aggregation for retries/re-runs of the same extracted batch.
@task(
    name="transform-business-kpis",
    retries=0,
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(hours=1),
    persist_result=True,
    result_serializer="pickle",
)
def transform_business_kpis(
    records: list[dict[str, Any]], week_start: date
) -> dict[str, Any]:
    """Validate records and aggregate the four KPIs; cached for one hour."""
    rows, counts = validate_and_aggregate(records, week_start)
    return {"rows": rows, **counts, "week_start": week_start}


# Three retries with 1/5/15-second backoff handle temporary reporting DB outages;
# transactional, idempotent partition replacement makes repeating the load safe.
@task(name="load-week-partition", retries=3, retry_delay_seconds=[1, 5, 15])
def load_week_partition(aggregate: dict[str, Any], run_id: str) -> int:
    """Atomically replace the weekly reporting partition using PostgreSQL."""
    reporting_url = _database_url("REPORTING_DATABASE_URL")
    engine = create_engine(reporting_url, pool_pre_ping=True)
    week_start = aggregate["week_start"]
    rows = aggregate["rows"]
    if rows and any(row["week_start"] != week_start for row in rows):
        raise ValueError("All output rows must belong to the selected week")
    columns = (
        "office",
        "programme_id",
        "week_start",
        "total_material_cost",
        "kits_delivered_count",
        "shortage_events_count",
        "cost_variance_events_count",
        "currency",
    )
    insert_sql = text(
        """INSERT INTO reporting.weekly_office_program_performance
           (office, programme_id, week_start, total_material_cost,
            kits_delivered_count, shortage_events_count,
            cost_variance_events_count, currency, computed_at)
           VALUES (:office, :programme_id, :week_start, :total_material_cost,
                   :kits_delivered_count, :shortage_events_count,
                   :cost_variance_events_count, :currency, now())
           ON CONFLICT (office, programme_id, week_start) DO UPDATE SET
             total_material_cost = EXCLUDED.total_material_cost,
             kits_delivered_count = EXCLUDED.kits_delivered_count,
             shortage_events_count = EXCLUDED.shortage_events_count,
             cost_variance_events_count = EXCLUDED.cost_variance_events_count,
             currency = EXCLUDED.currency,
             computed_at = now()"""
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"weekly-office-program-performance:{week_start}"},
            )
            connection.execute(
                text("DELETE FROM reporting.weekly_office_program_performance WHERE week_start = :week_start"),
                {"week_start": week_start},
            )
            for row in rows:
                connection.execute(insert_sql, {key: row[key] for key in columns})
            audit_update = connection.execute(
                text(
                    """UPDATE reporting.pipeline_runs
                       SET status = 'Completed', ended_at = now(),
                           processed_records = :processed_records,
                           accepted_records = :accepted_records,
                           rejected_records = :rejected_records,
                           rows_written = :rows_written
                       WHERE run_id = :run_id AND week_start = :week_start
                         AND status IN ('Running', 'Completed')"""
                ),
                {
                    "run_id": run_id,
                    "week_start": week_start,
                    "processed_records": aggregate["processed_records"],
                    "accepted_records": aggregate["accepted_records"],
                    "rejected_records": aggregate["rejected_records"],
                    "rows_written": len(rows),
                },
            )
            if audit_update.rowcount != 1:
                raise RuntimeError("Pipeline run audit row was not updated")
        return len(rows)
    finally:
        engine.dispose()


# Two short retries give the audit DB a chance to recover without masking the
# original pipeline failure or delaying its propagation for long.
@task(name="mark-pipeline-run-failed", retries=2, retry_delay_seconds=[1, 5])
def mark_pipeline_run_failed(run_id: str, error: Exception) -> None:
    """Persist a sanitized failure status without logging exception payloads."""
    reporting_url = _database_url("REPORTING_DATABASE_URL")
    engine = create_engine(reporting_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE reporting.pipeline_runs
                       SET status = 'Failed', ended_at = now(),
                           error_code = :error_code, error_message = :error_message
                       WHERE run_id = :run_id AND status = 'Running'"""
                ),
                {
                    "run_id": run_id,
                    "error_code": type(error).__name__[:64],
                    "error_message": "Pipeline stage failed; inspect sanitized Prefect task logs.",
                },
            )
    finally:
        engine.dispose()


@task(name="write-evaluation-artifact", retries=0)
def write_evaluation_artifact(aggregate: dict[str, Any], rows_written: int, run_id: str) -> str:
    """Optional, non-critical local JSON summary for pipeline evaluation."""
    import json
    from pathlib import Path

    output_dir = Path(__file__).resolve().parents[1] / "eval"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"business-performance-{aggregate['week_start'].isoformat()}-{run_id}.json"
    payload = {
        key: value
        for key, value in aggregate.items()
        if key != "rows"
    }
    payload["rows_written"] = rows_written
    path.write_text(json.dumps(payload, default=str, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _result_or_raise(state: State[Any]) -> Any:
    """Return a successful task result or re-raise its captured failure."""
    if state.is_failed():
        result = state.result(raise_on_failure=False)
        if isinstance(result, BaseException):
            raise result
        raise RuntimeError("Pipeline load task failed without an exception result")
    return state.result()


@flow(name="weekly_office_program_performance", log_prints=True)
def weekly_office_program_performance(week_start: date | str | None = None) -> dict[str, Any]:
    """Extract, transform, and load the selected weekly reporting partition."""
    logger = get_run_logger()
    resolved_week = resolve_week(week_start)
    run_id = str(get_run_context().flow_run.id)
    start_pipeline_run(resolved_week, run_id)
    try:
        extracted = extract_events(resolved_week)
        aggregate = transform_business_kpis(extracted, resolved_week)
        # Capture this task's terminal state so the flow can persist the failed audit
        # status before re-raising, instead of allowing Prefect to short-circuit.
        load_state = load_week_partition.with_options(return_state=True)(aggregate, run_id)
        rows_written = _result_or_raise(load_state)
    except Exception as exc:
        try:
            mark_pipeline_run_failed(run_id, exc)
        except Exception as audit_exc:
            logger.error("Could not persist failed run status: %s", type(audit_exc).__name__)
        raise

    # Evaluation artifacts are useful but must never block KPI publication.
    try:
        artifact = write_evaluation_artifact.with_options(
            return_state=True, raise_on_failure=False
        )(aggregate, rows_written, run_id)
        if artifact.is_failed():
            logger.warning("Optional evaluation artifact task failed; continuing pipeline")
            artifact = None
        else:
            # return_state=True returns a Prefect State, not the task's path.
            artifact = artifact.result()
    except Exception as exc:  # Optional task failures are intentionally isolated.
        logger.warning("Optional evaluation artifact failed: %s", type(exc).__name__)
        artifact = None

    return {
        "run_id": run_id,
        "week_start": resolved_week.isoformat(),
        "processed_records": aggregate["processed_records"],
        "accepted_records": aggregate["accepted_records"],
        "rejected_records": aggregate["rejected_records"],
        "duplicate_records": aggregate["duplicate_records"],
        "rows_written": rows_written,
        "evaluation_artifact": artifact,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run weekly Nexova business performance pipeline")
    parser.add_argument("week_start", nargs="?", help="ISO week Monday (YYYY-MM-DD); defaults to the last completed week")
    args = parser.parse_args()
    result = weekly_office_program_performance(args.week_start)
    print(result)


if __name__ == "__main__":
    main()