from datetime import date
from unittest.mock import MagicMock

import pytest

from services import job_runner


def _install_engine(monkeypatch, connection):
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    engine.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(job_runner, "_engine", lambda: engine)
    return engine


def test_create_job_run_inserts_pending_and_returns_id(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = 41
    engine = _install_engine(monkeypatch, connection)

    assert job_runner.create_job_run("nightly_export", date(2026, 11, 5)) == 41
    assert "'pending'" in str(connection.execute.call_args.args[0])
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("helper", ["has_processing_lock", "has_completed_for_date"])
def test_state_queries_return_boolean(monkeypatch, helper):
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = 1
    _install_engine(monkeypatch, connection)

    if helper == "has_processing_lock":
        result = job_runner.has_processing_lock("nightly_export")
    else:
        result = job_runner.has_completed_for_date("nightly_report", date(2026, 11, 5))

    assert result is True
    if helper == "has_completed_for_date":
        assert connection.execute.call_args.args[1] == {
            "job_name": "nightly_report",
            "target_date": date(2026, 11, 5),
        }


def test_processing_lock_can_be_scoped_to_target_date(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = None
    _install_engine(monkeypatch, connection)

    assert not job_runner.has_processing_lock("nightly_export", date(2026, 11, 5))

    statement, params = connection.execute.call_args.args
    assert "target_date = :target_date" in str(statement)
    assert params == {"job_name": "nightly_export", "target_date": date(2026, 11, 5)}


def test_completed_check_uses_exact_job_and_date(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = None
    _install_engine(monkeypatch, connection)

    assert not job_runner.has_completed_for_date("nightly_report", date(2026, 11, 5))

    statement, params = connection.execute.call_args.args
    assert "job_name = :job_name AND target_date = :target_date" in str(statement)
    assert "status = 'completed'" in str(statement)
    assert params == {"job_name": "nightly_report", "target_date": date(2026, 11, 5)}


def test_get_job_run_returns_mapping_or_none(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "id": 41,
        "status": "processing",
    }
    _install_engine(monkeypatch, connection)

    assert job_runner.get_job_run(41) == {"id": 41, "status": "processing"}


def test_update_job_run_rejects_missing_run(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.rowcount = 0
    _install_engine(monkeypatch, connection)

    with pytest.raises(RuntimeError, match="does not exist"):
        job_runner.update_job_run(99, "failed", "missing")


def test_update_job_run_sets_failed_message_and_finish_time(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.rowcount = 1
    _install_engine(monkeypatch, connection)

    job_runner.update_job_run(41, "failed", "RuntimeError: boom")

    params = connection.execute.call_args.args[1]
    assert params["status"] == "failed"
    assert params["error_message"] == "RuntimeError: boom"
    assert params["finished_at"] is not None


def test_run_job_marks_failure_logs_and_propagates(monkeypatch, caplog):
    monkeypatch.setattr(
        job_runner,
        "acquire_job_run",
        lambda *_: job_runner.JobRunAcquisition(41),
    )
    finish = MagicMock()
    monkeypatch.setattr(job_runner, "finish_job_run", finish)

    def fail():
        raise RuntimeError("pipeline failure")

    with pytest.raises(RuntimeError, match="pipeline failure"):
        job_runner.run_job("nightly_export", date(2026, 11, 5), fail)

    assert finish.call_args.args == (41, "failed", "RuntimeError: pipeline failure")
    assert "Background job for 2026-11-05 failed" in caplog.text
    assert "job=nightly_export status=failed" in caplog.text
    assert "Traceback" in caplog.text


def test_run_job_logs_state_update_failure_and_still_propagates(monkeypatch, caplog):
    monkeypatch.setattr(
        job_runner,
        "acquire_job_run",
        lambda *_: job_runner.JobRunAcquisition(41),
    )
    monkeypatch.setattr(
        job_runner,
        "finish_job_run",
        MagicMock(side_effect=RuntimeError("state database unavailable")),
    )

    with pytest.raises(ValueError, match="original failure"):
        job_runner.run_job(
            "nightly_export",
            date(2026, 11, 5),
            lambda: (_ for _ in ()).throw(ValueError("original failure")),
        )

    assert "Could not mark job run 41 as failed" in caplog.text