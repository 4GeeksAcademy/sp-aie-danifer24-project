from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import job_runner as job_runs


def test_acquire_job_run_claims_pending_target(monkeypatch):
    calls = []

    def completed(*_):
        return False

    def processing(*args):
        calls.append(args)
        return False

    monkeypatch.setattr(job_runs, "has_completed_for_date", completed)
    monkeypatch.setattr(job_runs, "has_processing_lock", processing)
    monkeypatch.setattr(job_runs, "create_job_run", lambda *_: 23)

    connection = MagicMock()
    connection.execute.side_effect = [
        SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {"id": 23, "status": "pending"})),
        SimpleNamespace(scalar_one_or_none=lambda: None),
        SimpleNamespace(scalar_one_or_none=lambda: 23),
    ]
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    monkeypatch.setattr(job_runs, "_engine", lambda: engine)

    result = job_runs.acquire_job_run("nightly_export", date(2026, 11, 5))

    assert result == job_runs.JobRunAcquisition(23)
    assert calls == [("nightly_export",)]
    assert connection.execute.call_count == 3
    assert "SET status = 'processing'" in str(connection.execute.call_args_list[-1].args[0])
    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    ("completed", "processing", "reason"),
    [(True, False, "already_completed"), (False, True, "processing")],
)
def test_acquire_job_run_skips_when_completed_or_locked(
    monkeypatch, completed, processing, reason
):
    monkeypatch.setattr(job_runs, "has_completed_for_date", lambda *_: completed)
    monkeypatch.setattr(job_runs, "has_processing_lock", lambda *_: processing)
    create = MagicMock()
    monkeypatch.setattr(job_runs, "create_job_run", create)

    result = job_runs.acquire_job_run("nightly_export", date(2026, 11, 5))

    assert result == job_runs.JobRunAcquisition(None, reason)
    create.assert_not_called()


def test_acquire_job_run_reports_exact_completed_date(monkeypatch):
    completed_check = MagicMock(return_value=True)
    monkeypatch.setattr(job_runs, "has_completed_for_date", completed_check)

    result = job_runs.acquire_job_run("nightly_report", date(2026, 11, 5))

    assert result == job_runs.JobRunAcquisition(None, "already_completed")
    completed_check.assert_called_once_with("nightly_report", date(2026, 11, 5))


def test_finish_job_run_updates_state_and_rejects_invalid_status(monkeypatch):
    update = MagicMock()
    monkeypatch.setattr(job_runs, "update_job_run", update)

    job_runs.finish_job_run(23, "failed", "RuntimeError: test failure")

    update.assert_called_once_with(23, "failed", "RuntimeError: test failure")
    with pytest.raises(ValueError, match="only finish"):
        job_runs.finish_job_run(23, "pending")


def test_run_job_marks_completed_on_success(monkeypatch):
    monkeypatch.setattr(job_runs, "acquire_job_run", lambda *_: job_runs.JobRunAcquisition(23))
    finish = MagicMock()
    monkeypatch.setattr(job_runs, "finish_job_run", finish)

    acquisition, result = job_runs.run_job("nightly_export", date(2026, 11, 5), lambda: "ok")

    assert acquisition == job_runs.JobRunAcquisition(23)
    assert result == "ok"
    finish.assert_called_once_with(23, "completed")
