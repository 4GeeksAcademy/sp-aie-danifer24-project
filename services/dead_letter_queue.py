"""PostgreSQL persistence for Celery tasks that exhausted their retries."""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)


def _safe_error(error: BaseException) -> str:
    message = f"{type(error).__name__}: {error}"
    message = re.sub(
        r"(?i)(postgres(?:ql)?(?:\+[^:/@]+)?://[^:/@]+:)[^@/]+@",
        r"\1***@",
        message,
    )
    return message[:4000]


def record_dead_letter(task_id: str, attempt: int, error: BaseException) -> None:
    """Persist one terminal task failure after Celery exhausts retries."""
    database_url = os.getenv("JOB_RUNS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("JOB_RUNS_DATABASE_URL or DATABASE_URL must be set")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Dead-letter storage must use PostgreSQL")

    engine = create_engine(
        url.set(drivername="postgresql+psycopg2"),
        pool_pre_ping=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO public.celery_dead_letters
                           (task_id, attempt, error_message)
                       VALUES (:task_id, :attempt, :error_message)
                       ON CONFLICT (task_id) DO UPDATE
                       SET attempt = EXCLUDED.attempt,
                           error_message = EXCLUDED.error_message,
                           failed_at = now()"""
                ),
                {
                    "task_id": task_id,
                    "attempt": attempt,
                    "error_message": _safe_error(error),
                },
            )
    finally:
        engine.dispose()


def log_dead_letter_persistence_failure(task_id: str, error: BaseException) -> None:
    """Log persistence failures without masking the original task exception."""
    logger.exception(
        "Failed to persist Celery dead letter for task_id=%s: %s",
        task_id,
        _safe_error(error),
    )
