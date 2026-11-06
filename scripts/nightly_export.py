#!/usr/bin/env python3
"""Export yesterday's telemetry and trigger the existing ETL as a subprocess.

The CSV is an immutable daily backup/audit snapshot. The ETL reads source events
from PostgreSQL itself and never consumes this CSV. Schedule this standalone
script with cron or an external scheduler; it is not run inside FastAPI.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from services.job_runner import (
    JOB_NAME,
    JobRunAcquisition,
    run_job,
)

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIRECTORY = ROOT / "data" / "raw"
CSV_COLUMNS = (
    "event_id",
    "event_type",
    "timestamp",
    "service",
    "tags",
    "session_id",
    "user_id",
    "schema_version",
    "request_id",
)
PIPELINE_COMMAND = (sys.executable, "data/pipelines/pipeline.py")
logger = logging.getLogger(__name__)


class UTCFormatter(logging.Formatter):
    """Render log timestamps in UTC for consistent scheduler observability."""

    converter = time_module.gmtime

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "job_name"):
            record.job_name = JOB_NAME
        if not hasattr(record, "job_status"):
            record.job_status = "unknown"
        return super().format(record)


def configure_logging() -> None:
    """Configure standalone CLI logs; respect handlers installed by callers."""
    logging.basicConfig(level=logging.INFO)
    formatter = UTCFormatter(
        "%(asctime)sZ %(levelname)s job=%(job_name)s status=%(job_status)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def resolve_target_date(value: str | None = None, *, now: datetime | None = None) -> date:
    """Resolve TARGET_DATE or yesterday according to the UTC calendar."""
    if value:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("TARGET_DATE must be an ISO date (YYYY-MM-DD)")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("TARGET_DATE must be an ISO date (YYYY-MM-DD)") from error
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(timezone.utc).date() - timedelta(days=1)


def _telemetry_engine():
    value = os.getenv("TELEMETRY_DATABASE_URL")
    if not value:
        raise RuntimeError("TELEMETRY_DATABASE_URL must be configured for CSV export")
    if os.getenv("TELEMETRY_DATABASE_READ_ONLY", "").lower() != "true":
        raise RuntimeError("TELEMETRY_DATABASE_READ_ONLY=true is required")
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Telemetry source must use PostgreSQL")
    return create_engine(url.set(drivername="postgresql+psycopg2"), pool_pre_ping=True)


def export_telemetry(target_date: date, destination: Path | None = None) -> Path:
    """Create a CSV snapshot once; existing snapshots are never overwritten."""
    output = destination or EXPORT_DIRECTORY / f"telemetry_{target_date.isoformat()}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        return output

    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    engine = _telemetry_engine()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(temporary_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """SELECT event_id, event_type, timestamp, service, tags,
                                  session_id, user_id, schema_version, request_id
                           FROM public.telemetry_events
                           WHERE timestamp >= :start AND timestamp < :end
                           ORDER BY timestamp, event_id"""
                    ),
                    {"start": start, "end": end},
                ).mappings()
                for row in rows:
                    record = dict(row)
                    record["tags"] = json.dumps(record["tags"], sort_keys=True, default=str)
                    writer.writerow(record)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        try:
            # Hard-link is atomic and will not overwrite a snapshot if another
            # writer created it after the initial existence check.
            os.link(temporary_path, output)
        except FileExistsError:
            pass
        return output
    finally:
        engine.dispose()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run_pipeline(target_date: date, command: Sequence[str] = PIPELINE_COMMAND) -> None:
    """Launch the repository's real ETL CLI in a separate process."""
    # The repository currently exposes a weekly ETL. Pass the ISO Monday for
    # the requested day explicitly instead of letting it default to last week.
    week_start = target_date - timedelta(days=target_date.weekday())
    subprocess.run((*command, week_start.isoformat()), cwd=ROOT, check=True)


def _safe_error_message(error: BaseException) -> str:
    """Keep useful exception context while masking credentials in DB URLs."""
    message = f"{type(error).__name__}: {error}"
    return re.sub(
        r"(?i)(postgres(?:ql)?(?:\+[^:/@]+)?://[^:/@]+:)[^@/]+@",
        r"\1***@",
        message,
    )[:4000]


def run_nightly(target_date: date) -> str:
    """Run one day; return completed, skipped (idempotent), or failed."""
    logger.info(
        "Nightly job started for target_date=%s",
        target_date.isoformat(),
        extra={"job_name": JOB_NAME, "job_status": "processing"},
    )

    def work() -> None:
        export_telemetry(target_date)
        # The weekly business-performance ETL reads from telemetry_events in the
        # database and chooses its most recently completed week independently.
        run_pipeline(target_date)

    acquisition, _ = run_job(JOB_NAME, target_date, work)
    if acquisition.run_id is None:
        logger.info(
            "Nightly job omitted: reason=%s target_date=%s",
            acquisition.skip_reason,
            target_date.isoformat(),
            extra={"job_name": JOB_NAME, "job_status": "skipped"},
        )
        return "skipped"

    logger.info(
        "Nightly job finished for target_date=%s run_id=%s",
        target_date.isoformat(),
        acquisition.run_id,
        extra={"job_name": JOB_NAME, "job_status": "completed"},
    )
    return "completed"


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Export daily telemetry and launch the ETL")
    parser.add_argument(
        "--target-date",
        help="target day in UTC (overrides TARGET_DATE; defaults to yesterday)",
    )
    args = parser.parse_args(argv)
    try:
        target_date = resolve_target_date(args.target_date or os.getenv("TARGET_DATE"))
        result = run_nightly(target_date)
    except Exception as error:
        logger.exception(
            "Nightly job failed: %s",
            _safe_error_message(error),
            extra={"job_name": JOB_NAME, "job_status": "failed"},
        )
        return 1
    return 1 if result == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
