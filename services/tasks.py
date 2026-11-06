"""Celery tasks for background processing."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from celery import Task

from data.pipelines.prefect_client import start_weekly_office_program_performance
from scripts.nightly_export import resolve_target_date, run_nightly
from services.celery_app import celery_app
from services.dead_letter_queue import (
    log_dead_letter_persistence_failure,
    record_dead_letter,
)

logger = logging.getLogger(__name__)


class ObservableTask(Task):
    """Emit a structured lifecycle log for each task attempt."""

    abstract = True

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        self._attempt_started_at = time.monotonic()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._attempt_started_at = time.monotonic()
        return super().__call__(*args, **kwargs)

    def _log_attempt(
        self,
        task_id: str,
        state: str,
        *,
        error: BaseException | None = None,
        exc_info: Any = None,
    ) -> None:
        started_at = getattr(self, "_attempt_started_at", None)
        duration_seconds = time.monotonic() - started_at if started_at else 0.0
        extra = {
            "task_id": task_id,
            "attempt": self.request.retries + 1,
            "task_state": state,
            "duration_seconds": round(duration_seconds, 3),
        }
        if error is None:
            logger.info(
                "Celery task finished task_id=%s attempt=%s state=%s duration_seconds=%.3f",
                task_id,
                extra["attempt"],
                state,
                duration_seconds,
                extra=extra,
            )
        else:
            logger.error(
                "Celery task finished task_id=%s attempt=%s state=%s duration_seconds=%.3f error=%s",
                task_id,
                extra["attempt"],
                state,
                duration_seconds,
                error,
                extra=extra,
                exc_info=exc_info,
            )

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        self._log_attempt(task_id, "success")

    def on_retry(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        self._log_attempt(task_id, "retry", error=exc, exc_info=einfo.exc_info)

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        self._log_attempt(task_id, "failure", error=exc, exc_info=einfo.exc_info)


@celery_app.task(
    bind=True,
    base=ObservableTask,
    name="services.tasks.run_nightly_export",
    max_retries=3,
    default_retry_delay=1,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=3600,
    time_limit=3660,
)
def run_nightly_export(self, target_date: str | None = None) -> dict[str, str]:
    """Export telemetry and run the weekly ETL for a target day.

    ``target_date`` is a lightweight ISO date string; if omitted, the task
    uses the existing scheduler behavior (yesterday in UTC).
    """
    resolved_date: date | None = None
    try:
        resolved_date = resolve_target_date(target_date)
        result = run_nightly(resolved_date)
        return {"status": result, "target_date": resolved_date.isoformat()}
    except Exception as error:
        retries_used = self.request.retries
        if retries_used < self.max_retries:
            # Exponential backoff: 2, 4, then 8 seconds.
            raise self.retry(exc=error, countdown=2 ** (retries_used + 1))

        try:
            record_dead_letter(
                task_id=self.request.id or "unknown",
                attempt=retries_used + 1,
                error=error,
            )
        except Exception:
            log_dead_letter_persistence_failure(self.request.id or "unknown", error)
        logger.exception(
            "Celery task exhausted retries",
            extra={
                "task_id": self.request.id,
                "attempt": retries_used + 1,
                "target_date": resolved_date.isoformat() if resolved_date else target_date,
            },
        )
        raise


@celery_app.task(
    bind=True,
    base=ObservableTask,
    name="services.tasks.start_weekly_pipeline",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=330,
)
def start_weekly_pipeline(self, week_start: str | None = None) -> dict[str, str]:
    """Ask Prefect to run a weekly pipeline deployment from the worker."""
    try:
        parsed_week_start = date.fromisoformat(week_start) if week_start else None
        if parsed_week_start is not None and parsed_week_start.weekday() != 0:
            raise ValueError("week_start must be an ISO week Monday")
        result = start_weekly_office_program_performance(parsed_week_start)
        return {
            "run_id": result["run_id"],
            "flow_run_id": result["flow_run_id"],
            "status": result["status"],
            "week_start": result["week_start"].isoformat(),
        }
    except Exception as error:
        retries_used = self.request.retries
        if retries_used < self.max_retries:
            raise self.retry(exc=error, countdown=2 ** (retries_used + 1))

        try:
            record_dead_letter(
                task_id=self.request.id or "unknown",
                attempt=retries_used + 1,
                error=error,
            )
        except Exception:
            log_dead_letter_persistence_failure(self.request.id or "unknown", error)
        raise
