from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch


def authenticated_client(api, register, login):
    client, _, _ = api
    register(client)
    token = login(client).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_reporting_routes_require_authentication(api):
    client, _, _ = api
    paths = [
        ("GET", "/reporting/pipeline-runs/latest"),
        ("POST", "/reporting/pipeline-runs"),
        ("GET", "/reporting/weekly-office-program-performance"),
    ]
    for method, path in paths:
        response = client.request(method, path)
        assert response.status_code == 401


def test_latest_pipeline_run_returns_audit_metadata(api, register, login):
    client = authenticated_client(api, register, login)
    run = {
        "run_id": "prefect-run-123",
        "flow_name": "weekly_office_program_performance",
        "status": "Completed",
        "week_start": date(2026, 11, 2),
        "started_at": datetime(2026, 11, 9, 7, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 11, 9, 7, 0, 12, tzinfo=timezone.utc),
        "processed_records": 42,
        "accepted_records": 42,
        "rejected_records": 0,
        "rows_written": 6,
        "error_code": None,
        "error_message": None,
    }
    with patch("services.reporting.router.get_latest_pipeline_run", return_value=run):
        response = client.get("/reporting/pipeline-runs/latest")

    assert response.status_code == 200
    assert response.json()["run_id"] == "prefect-run-123"
    assert response.json()["rows_written"] == 6


def test_latest_pipeline_run_returns_404_when_no_runs(api, register, login):
    client = authenticated_client(api, register, login)
    with patch("services.reporting.router.get_latest_pipeline_run", return_value=None):
        response = client.get("/reporting/pipeline-runs/latest")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_manual_run_delegates_to_prefect_adapter(api, register, login):
    client = authenticated_client(api, register, login)
    expected = {
        "run_id": "flow-123",
        "flow_run_id": "flow-123",
        "status": "Running",
        "week_start": date(2026, 11, 2),
    }
    with patch(
        "services.reporting.router.start_weekly_office_program_performance",
        return_value=expected,
    ) as start_run:
        response = client.post(
            "/reporting/pipeline-runs", json={"week_start": "2026-11-02"}
        )

    assert response.status_code == 202
    assert response.json() == {
        "run_id": "flow-123",
        "flow_run_id": "flow-123",
        "status": "Running",
        "week_start": "2026-11-02",
    }
    start_run.assert_called_once_with(date(2026, 11, 2))


def test_manual_run_rejects_non_monday(api, register, login):
    client = authenticated_client(api, register, login)
    with patch(
        "services.reporting.router.start_weekly_office_program_performance",
        side_effect=ValueError("week_start must be an ISO week Monday"),
    ):
        response = client.post(
            "/reporting/pipeline-runs", json={"week_start": "2026-11-03"}
        )
    assert response.status_code == 422


def test_manual_run_hides_prefect_connection_errors(api, register, login):
    client = authenticated_client(api, register, login)
    with patch(
        "services.reporting.router.start_weekly_office_program_performance",
        side_effect=RuntimeError("private server detail"),
    ):
        response = client.post("/reporting/pipeline-runs", json={})
    assert response.status_code == 503
    assert "private server detail" not in response.text


def test_prefect_client_requests_configured_deployment(monkeypatch):
    from types import SimpleNamespace

    from data.pipelines.prefect_client import (
        start_weekly_office_program_performance,
    )

    calls = []

    def fake_run_deployment(name, **kwargs):
        calls.append((name, kwargs))
        return SimpleNamespace(id="prefect-flow-run-456")

    monkeypatch.setenv("BUSINESS_PERFORMANCE_DEPLOYMENT", "flow/prod")
    with patch("prefect.deployments.run_deployment", side_effect=fake_run_deployment):
        result = start_weekly_office_program_performance("2026-11-02")

    assert result == {
        "run_id": "prefect-flow-run-456",
        "flow_run_id": "prefect-flow-run-456",
        "status": "Running",
        "week_start": date(2026, 11, 2),
    }
    assert calls == [
        (
            "flow/prod",
            {
                "parameters": {"week_start": "2026-11-02"},
                "timeout": 0,
                "as_subflow": False,
            },
        )
    ]


def test_weekly_kpi_feed_matches_briefing_contract(api, register, login):
    client = authenticated_client(api, register, login)
    result = {
        "week_start": date(2026, 11, 2),
        "entries": [
            {
                "office": "valencia",
                "programme_id": "ventas-b2b",
                "total_material_cost": Decimal("1240.50"),
                "kits_delivered_count": 18,
                "shortage_events_count": 1,
                "cost_variance_events_count": 0,
                "currency": "EUR",
            }
        ],
    }
    with patch(
        "services.reporting.router.get_weekly_office_program_performance",
        return_value=result,
    ) as get_kpis:
        response = client.get(
            "/reporting/weekly-office-program-performance",
            params={"week_start": "2026-11-02"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "week_start": "2026-11-02",
        "entries": [
            {
                "office": "valencia",
                "programme_id": "ventas-b2b",
                "total_material_cost": 1240.5,
                "kits_delivered_count": 18,
                "shortage_events_count": 1,
                "cost_variance_events_count": 0,
                "currency": "EUR",
            }
        ],
    }
    get_kpis.assert_called_once_with(date(2026, 11, 2))
