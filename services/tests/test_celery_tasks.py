from datetime import date
from unittest.mock import MagicMock

import pytest

from services import dead_letter_queue
from services.tasks import run_nightly_export, start_weekly_pipeline


def test_task_uses_three_retries_and_exponential_countdown():
    assert run_nightly_export.max_retries == 3
    assert run_nightly_export.acks_late is True
    assert run_nightly_export.soft_time_limit == 3600
    assert run_nightly_export.time_limit == 3660


def test_task_retries_with_exponential_backoff(monkeypatch):
    retry = MagicMock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(run_nightly_export, "retry", retry)
    monkeypatch.setattr("services.tasks.resolve_target_date", lambda _: date(2026, 11, 5))
    monkeypatch.setattr(
        "services.tasks.run_nightly",
        MagicMock(side_effect=ValueError("temporary")),
    )

    run_nightly_export.push_request(id="task-123", retries=1)
    try:
        with pytest.raises(RuntimeError, match="retry scheduled"):
            run_nightly_export.run(target_date="2026-11-05")
    finally:
        run_nightly_export.pop_request()

    assert retry.call_args.kwargs["countdown"] == 4


def test_task_persists_dead_letter_after_retries_exhausted(monkeypatch):
    record = MagicMock()
    monkeypatch.setattr("services.tasks.record_dead_letter", record)
    monkeypatch.setattr("services.tasks.resolve_target_date", lambda _: date(2026, 11, 5))
    monkeypatch.setattr(
        "services.tasks.run_nightly",
        MagicMock(side_effect=ValueError("permanent failure")),
    )

    run_nightly_export.push_request(id="task-456", retries=3)
    try:
        with pytest.raises(ValueError, match="permanent failure"):
            run_nightly_export.run(target_date="2026-11-05")
    finally:
        run_nightly_export.pop_request()

    assert record.call_args.kwargs["task_id"] == "task-456"
    assert record.call_args.kwargs["attempt"] == 4
    assert isinstance(record.call_args.kwargs["error"], ValueError)


def test_dead_letter_storage_sanitizes_error_and_writes_attempt(monkeypatch):
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.example/test")
    monkeypatch.setattr(dead_letter_queue, "create_engine", lambda *args, **kwargs: engine)

    dead_letter_queue.record_dead_letter(
        "task-789",
        4,
        RuntimeError("postgresql://user:secret@db.example/test failed"),
    )

    query, params = connection.execute.call_args.args
    assert "celery_dead_letters" in str(query)
    assert params["task_id"] == "task-789"
    assert params["attempt"] == 4
    assert "secret" not in params["error_message"]
    engine.dispose.assert_called_once()


def test_weekly_pipeline_task_delegates_to_prefect(monkeypatch):
    expected = {
        "run_id": "flow-123",
        "flow_run_id": "flow-123",
        "status": "Running",
        "week_start": date(2026, 11, 2),
    }
    start = MagicMock(return_value=expected)
    monkeypatch.setattr("services.tasks.start_weekly_office_program_performance", start)

    result = start_weekly_pipeline.run(week_start="2026-11-02")

    start.assert_called_once_with(date(2026, 11, 2))
    assert result == {
        "run_id": "flow-123",
        "flow_run_id": "flow-123",
        "status": "Running",
        "week_start": "2026-11-02",
    }


def test_weekly_pipeline_task_retries_prefect_errors(monkeypatch):
    retry = MagicMock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(start_weekly_pipeline, "retry", retry)
    monkeypatch.setattr(
        "services.tasks.start_weekly_office_program_performance",
        MagicMock(side_effect=RuntimeError("temporary Prefect outage")),
    )
    start_weekly_pipeline.push_request(id="weekly-task", retries=1)
    try:
        with pytest.raises(RuntimeError, match="retry scheduled"):
            start_weekly_pipeline.run(week_start="2026-11-02")
    finally:
        start_weekly_pipeline.pop_request()

    assert retry.call_args.kwargs["countdown"] == 4
