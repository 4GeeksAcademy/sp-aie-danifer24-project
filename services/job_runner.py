"""Persistence and lifecycle helpers for background jobs.

The processing row in ``public.job_runs`` is the distributed lock. Daily
idempotency is keyed by ``(job_name, target_date)``; ETL-internal audit remains
in ``reporting.pipeline_runs``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, TypeVar

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)
T = TypeVar("T")
JOB_NAME = "nightly_export"


@dataclass(frozen=True)
class JobRunAcquisition:
    run_id: int | None
    skip_reason: str | None = None


def _engine():
    value = os.getenv("JOB_RUNS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("JOB_RUNS_DATABASE_URL or DATABASE_URL must be set")
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Job-run storage must use PostgreSQL")
    return create_engine(url.set(drivername="postgresql+psycopg2"), pool_pre_ping=True)


def create_job_run(job_name: str, target_date: date) -> int:
    """Create the pending row if absent and return its ID."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            run_id = connection.execute(
                text(
                    """INSERT INTO public.job_runs (job_name, target_date, status)
                       VALUES (:job_name, :target_date, 'pending')
                       ON CONFLICT (job_name, target_date) DO NOTHING
                       RETURNING id"""
                ),
                {"job_name": job_name, "target_date": target_date},
            ).scalar_one_or_none()
            if run_id is None:
                run_id = connection.execute(
                    text(
                        """SELECT id FROM public.job_runs
                           WHERE job_name = :job_name AND target_date = :target_date"""
                    ),
                    {"job_name": job_name, "target_date": target_date},
                ).scalar_one()
            return int(run_id)
    finally:
        engine.dispose()


def update_job_run(
    run_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update a job state; terminal updates set ``finished_at``."""
    if status not in {"pending", "processing", "completed", "failed"}:
        raise ValueError(f"Unsupported job-run status: {status}")
    finished_at = datetime.now(timezone.utc) if status in {"completed", "failed"} else None
    started_at = datetime.now(timezone.utc) if status == "processing" else None
    engine = _engine()
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """UPDATE public.job_runs
                       SET status = :status,
                           started_at = COALESCE(:started_at, started_at),
                           finished_at = :finished_at,
                           error_message = :error_message
                       WHERE id = :run_id"""
                ),
                {
                    "run_id": run_id,
                    "status": status,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "error_message": error_message,
                },
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Job run {run_id} does not exist")
    finally:
        engine.dispose()


def get_job_run(run_id: int) -> dict | None:
    """Return a job-run record by ID, or ``None`` when it does not exist."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM public.job_runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        engine.dispose()


def has_processing_lock(job_name: str, target_date: date | None = None) -> bool:
    """Check for a processing row, scoped to the whole job or one target day."""
    query = "SELECT 1 FROM public.job_runs WHERE job_name = :job_name AND status = 'processing'"
    params: dict[str, object] = {"job_name": job_name}
    if target_date is not None:
        query += " AND target_date = :target_date"
        params["target_date"] = target_date
    query += " LIMIT 1"
    engine = _engine()
    try:
        with engine.connect() as connection:
            return connection.execute(text(query), params).scalar_one_or_none() is not None
    finally:
        engine.dispose()


def has_completed_for_date(job_name: str, target_date: date) -> bool:
    """Check completion for the exact ``(job_name, target_date)`` pair."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            return connection.execute(
                text(
                    """SELECT 1 FROM public.job_runs
                       WHERE job_name = :job_name AND target_date = :target_date
                         AND status = 'completed'
                       LIMIT 1"""
                ),
                {"job_name": job_name, "target_date": target_date},
            ).scalar_one_or_none() is not None
    finally:
        engine.dispose()


def acquire_job_run(job_name: str, target_date: date) -> JobRunAcquisition:
    """Acquire processing state, skipping a held lock or completed date."""
    if has_completed_for_date(job_name, target_date):
        return JobRunAcquisition(None, "already_completed")
    if has_processing_lock(job_name):
        return JobRunAcquisition(None, "processing")

    run_id = create_job_run(job_name, target_date)
    engine = _engine()
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                text(
                    """SELECT id, status FROM public.job_runs
                       WHERE id = :run_id FOR UPDATE"""
                ),
                {"run_id": run_id},
            ).mappings().one()
            if existing["status"] == "completed":
                return JobRunAcquisition(None, "already_completed")
            if existing["status"] == "processing":
                return JobRunAcquisition(None, "processing")
            if connection.execute(
                text(
                    """SELECT 1 FROM public.job_runs
                       WHERE job_name = :job_name AND status = 'processing'
                       LIMIT 1"""
                ),
                {"job_name": job_name},
            ).scalar_one_or_none() is not None:
                return JobRunAcquisition(None, "processing")
            claimed = connection.execute(
                text(
                    """UPDATE public.job_runs
                       SET status = 'processing', started_at = :started_at,
                           finished_at = NULL, error_message = NULL
                       WHERE id = :run_id AND status IN ('pending', 'failed')
                       RETURNING id"""
                ),
                {"run_id": run_id, "started_at": datetime.now(timezone.utc)},
            ).scalar_one_or_none()
            if claimed is None:
                return JobRunAcquisition(None, "processing")
            return JobRunAcquisition(int(claimed))
    except IntegrityError:
        # The partial unique index rejected a competing processing claim.
        return JobRunAcquisition(None, "processing")
    finally:
        engine.dispose()


def finish_job_run(run_id: int, status: str, error_message: str | None = None) -> None:
    if status not in {"completed", "failed"}:
        raise ValueError("A job run can only finish as completed or failed")
    update_job_run(run_id, status, error_message)


def run_job(job_name: str, target_date: date, work: Callable[[], T]) -> tuple[JobRunAcquisition, T | None]:
    """Acquire and execute work, persisting failure before propagating errors."""
    acquisition = acquire_job_run(job_name, target_date)
    if acquisition.run_id is None:
        return acquisition, None
    run_id = acquisition.run_id
    try:
        result = work()
        finish_job_run(run_id, "completed")
        return acquisition, result
    except BaseException as error:
        try:
            message = f"{type(error).__name__}: {error}"
            message = re.sub(
                r"(?i)(postgres(?:ql)?(?:\+[^:/@]+)?://[^:/@]+:)[^@/]+@",
                r"\1***@",
                message,
            )[:4000]
            finish_job_run(run_id, "failed", message)
        except Exception:
            logger.exception(
                "Could not mark job run %s as failed",
                run_id,
                extra={"job_name": job_name, "job_status": "failed"},
            )
        logger.exception(
            "Background job for %s failed",
            target_date.isoformat(),
            extra={"job_name": job_name, "job_status": "failed"},
        )
        raise
