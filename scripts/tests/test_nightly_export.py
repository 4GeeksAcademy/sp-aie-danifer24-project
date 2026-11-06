import csv
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts import nightly_export


def test_resolve_target_date_uses_previous_utc_day():
    now = datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)
    assert nightly_export.resolve_target_date(now=now) == date(2026, 11, 5)


def test_resolve_target_date_converts_aware_time_to_utc():
    local_time = datetime.fromisoformat("2026-11-06T00:30:00+02:00")
    assert nightly_export.resolve_target_date(now=local_time) == date(2026, 11, 4)


def test_resolve_target_date_rejects_naive_clock_and_invalid_date():
    with pytest.raises(ValueError, match="timezone-aware"):
        nightly_export.resolve_target_date(now=datetime(2026, 11, 6))
    with pytest.raises(ValueError, match="ISO date"):
        nightly_export.resolve_target_date("06-11-2026")
    with pytest.raises(ValueError, match="ISO date"):
        nightly_export.resolve_target_date("2026-1-5")


def test_export_telemetry_writes_filtered_snapshot_once(tmp_path, monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = [
        {
            "event_id": "event-1",
            "event_type": "test",
            "timestamp": datetime(2026, 11, 5, 1, tzinfo=timezone.utc),
            "service": "api",
            "tags": {"safe": "value"},
            "session_id": None,
            "user_id": None,
            "schema_version": "1",
            "request_id": "request-1",
        }
    ]
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    engine.begin.return_value.__enter__.return_value = connection
    monkeypatch.setattr(nightly_export, "_telemetry_engine", lambda: engine)

    destination = tmp_path / "telemetry.csv"
    result = nightly_export.export_telemetry(date(2026, 11, 5), destination)
    assert result == destination
    with destination.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["event_id"] == "event-1"
    assert rows[0]["tags"] == '{"safe": "value"}'
    assert "timestamp < :end" in str(connection.execute.call_args.args[0])

    # A pre-existing backup is not read or replaced.
    destination.write_text("original backup\n", encoding="utf-8")
    assert nightly_export.export_telemetry(date(2026, 11, 5), destination) == destination
    assert destination.read_text(encoding="utf-8") == "original backup\n"
    assert engine.dispose.call_count == 1


def test_export_requires_read_only_source(monkeypatch):
    monkeypatch.setenv("TELEMETRY_DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.setenv("TELEMETRY_DATABASE_READ_ONLY", "false")
    with pytest.raises(RuntimeError, match="READ_ONLY=true"):
        nightly_export._telemetry_engine()


def test_pipeline_command_uses_iso_week_for_target_day(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(nightly_export.subprocess, "run", run)
    nightly_export.run_pipeline(date(2026, 11, 5))
    args, kwargs = run.call_args
    assert args[0] == (
        nightly_export.sys.executable,
        "data/pipelines/pipeline.py",
        "2026-11-02",
    )
    assert kwargs["cwd"] == nightly_export.ROOT
    assert kwargs["check"] is True


def test_duplicate_run_is_reported_as_skipped(monkeypatch, caplog):
    runner = MagicMock(
        return_value=(nightly_export.JobRunAcquisition(None, "processing"), None)
    )
    monkeypatch.setattr(nightly_export, "run_job", runner)
    export = MagicMock()
    monkeypatch.setattr(nightly_export, "export_telemetry", export)
    pipeline = MagicMock()
    monkeypatch.setattr(nightly_export, "run_pipeline", pipeline)

    with caplog.at_level("INFO", logger=nightly_export.__name__):
        assert nightly_export.run_nightly(date(2026, 11, 5)) == "skipped"
    skip = next(record for record in caplog.records if "omitted" in record.message)
    assert skip.levelname == "INFO"
    assert skip.job_name == nightly_export.JOB_NAME
    assert skip.job_status == "skipped"
    export.assert_not_called()
    pipeline.assert_not_called()


def test_nightly_delegates_work_to_job_runner_and_logs_completion(monkeypatch, caplog):
    calls = []

    def runner(job_name, target_date, work):
        calls.append((job_name, target_date))
        work()
        return nightly_export.JobRunAcquisition(7), None

    monkeypatch.setattr(nightly_export, "run_job", runner)
    monkeypatch.setattr(nightly_export, "export_telemetry", lambda *_: Path("backup.csv"))
    pipeline = MagicMock()
    monkeypatch.setattr(nightly_export, "run_pipeline", pipeline)

    with caplog.at_level("INFO", logger=nightly_export.__name__):
        assert nightly_export.run_nightly(date(2026, 11, 5)) == "completed"
    assert calls == [(nightly_export.JOB_NAME, date(2026, 11, 5))]
    pipeline.assert_called_once_with(date(2026, 11, 5))
    lifecycle = [record for record in caplog.records if record.name == nightly_export.__name__]
    assert [record.job_status for record in lifecycle] == ["processing", "completed"]
    assert all(record.job_name == nightly_export.JOB_NAME for record in lifecycle)


def test_main_resolves_target_date_from_environment(monkeypatch):
    monkeypatch.setenv("TARGET_DATE", "2026-11-05")
    run = MagicMock(return_value="skipped")
    monkeypatch.setattr(nightly_export, "run_nightly", run)
    assert nightly_export.main([]) == 0
    run.assert_called_once_with(date(2026, 11, 5))


def test_main_logs_exceptions_as_error_with_job_context(monkeypatch, caplog):
    run = MagicMock(side_effect=RuntimeError("pipeline failed"))
    monkeypatch.setattr(nightly_export, "run_nightly", run)

    with caplog.at_level("INFO"):
        assert nightly_export.main(["--target-date", "2026-11-05"]) == 1

    record = next(record for record in caplog.records if "Nightly job failed" in record.message)
    assert record.levelname == "ERROR"
    assert record.job_name == nightly_export.JOB_NAME
    assert record.job_status == "failed"
    assert record.exc_info is not None


def test_configured_log_format_has_timestamp_job_and_status(monkeypatch):
    root = nightly_export.logging.getLogger()
    handler = nightly_export.logging.StreamHandler()
    monkeypatch.setattr(root, "handlers", [handler])

    nightly_export.configure_logging()
    record = nightly_export.logging.LogRecord(
        nightly_export.__name__,
        nightly_export.logging.INFO,
        __file__,
        1,
        "started",
        (),
        None,
    )
    record.job_name = "nightly_export"
    record.job_status = "processing"

    rendered = handler.formatter.format(record)
    assert "Z INFO job=nightly_export status=processing started" in rendered
    assert rendered[:4] == "2026" or rendered[:4].isdigit()


def test_safe_error_message_masks_postgres_credentials():
    error = RuntimeError("connect postgresql://role:secret-pass@db.example/path")
    message = nightly_export._safe_error_message(error)
    assert "secret-pass" not in message
    assert "role:***@" in message
