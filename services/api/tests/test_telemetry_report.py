from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from services.api.database import get_db
from services.api.main import app
from services.api.models import TelemetryEventRecord
from services.api.routes.telemetry import report_cache


UTC = timezone.utc


def make_report_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def insert_event(session, event_id, event_type, timestamp, tags):
    session.add(
        TelemetryEventRecord(
            event_id=event_id,
            event_type=event_type,
            timestamp=timestamp,
            service="backoffice",
            tags=tags,
            session_id=None,
            user_id=None,
            schema_version="1.0.0",
            request_id=f"request-{event_id}",
        )
    )
    session.commit()


def test_report_returns_requested_metrics_and_filters_half_open_utc_window(api):
    client, _, _ = api
    engine = make_report_engine()
    start = datetime(2026, 11, 1, tzinfo=UTC)
    end = datetime(2026, 11, 3, tzinfo=UTC)
    with Session(engine) as session:
        insert_event(session, "in", "api_request_completed", start, {"status_code": 200})
        insert_event(session, "error", "api_request_completed", datetime(2026, 11, 2, tzinfo=UTC), {"status_code": 503})
        insert_event(session, "outside", "api_request_completed", end, {"status_code": 500})

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    report_cache.clear()
    try:
        response = client.get("/telemetry/report", params={"start_date": start.isoformat(), "end_date": end.isoformat()})

        assert response.status_code == 200
        assert response.json() == {
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "metrics": {
                "events_per_day": [
                    {"date": "2026-11-01", "event_type": "api_request_completed", "event_count": 1},
                    {"date": "2026-11-02", "event_type": "api_request_completed", "event_count": 1},
                ],
                "error_rate_by_type": [
                    {"date": "2026-11-01", "event_type": "api_request_completed", "event_count": 1, "error_count": 0, "error_rate": 0.0},
                    {"date": "2026-11-02", "event_type": "api_request_completed", "event_count": 1, "error_count": 1, "error_rate": 1.0},
                ],
            },
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        report_cache.clear()
        engine.dispose()


def test_report_cache_avoids_recalculating_same_window(api):
    client, _, _ = api
    report_cache.clear()
    start, end = "2026-11-01T00:00:00Z", "2026-11-03T00:00:00Z"
    with patch("services.api.routes.telemetry.events_per_day", return_value=[{"cached": True}]) as events_metric, patch(
        "services.api.routes.telemetry.error_rate_by_type", return_value=[]
    ) as errors_metric:
        first = client.get("/telemetry/report", params={"start_date": start, "end_date": end})
        second = client.get("/telemetry/report", params={"start_date": start, "end_date": end})

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert events_metric.call_count == 1
    assert errors_metric.call_count == 1
    report_cache.clear()


def test_report_cache_reuses_default_window_requests(api):
    client, _, _ = api
    report_cache.clear()
    with patch("services.api.routes.telemetry.events_per_day", return_value=[]) as events_metric, patch(
        "services.api.routes.telemetry.error_rate_by_type", return_value=[]
    ) as errors_metric:
        first = client.get("/telemetry/report")
        second = client.get("/telemetry/report")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert events_metric.call_count == 1
    assert errors_metric.call_count == 1
    report_cache.clear()


def test_report_rejects_invalid_or_reversed_ranges(api):
    client, _, _ = api

    invalid_format = client.get("/telemetry/report", params={"start_date": "not-a-date"})
    reversed_range = client.get(
        "/telemetry/report",
        params={"start_date": "2026-11-03T00:00:00Z", "end_date": "2026-11-01T00:00:00Z"},
    )

    assert invalid_format.status_code == 422
    assert reversed_range.status_code == 422


def test_error_rate_by_type_counts_catalogued_operational_errors():
    from services.telemetry.analysis import error_rate_by_type

    start = datetime(2026, 11, 1, tzinfo=UTC)
    end = datetime(2026, 11, 2, tzinfo=UTC)
    frame = pd.DataFrame(
        [
            {"timestamp": start, "event_type": "api_request_completed", "tags": {"status_code": 503}},
            {"timestamp": start, "event_type": "api_request_completed", "tags": {"status_code": 200}},
            {"timestamp": start, "event_type": "frontend_data_load_completed", "tags": {"outcome": "error"}},
            {"timestamp": start, "event_type": "frontend_unhandled_error", "tags": {}},
        ]
    )
    with patch("services.telemetry.analysis._load_events", return_value=frame):
        result = error_rate_by_type(object(), start, end)

    assert result == [
        {"date": "2026-11-01", "event_type": "api_request_completed", "event_count": 2, "error_count": 1, "error_rate": 0.5},
        {"date": "2026-11-01", "event_type": "frontend_data_load_completed", "event_count": 1, "error_count": 1, "error_rate": 1.0},
        {"date": "2026-11-01", "event_type": "frontend_unhandled_error", "event_count": 1, "error_count": 1, "error_rate": 1.0},
    ]
