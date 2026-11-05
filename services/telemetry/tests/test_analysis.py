import pandas as pd

from services.telemetry.analysis import (
    api_request_latency,
    api_request_server_errors,
    api_request_volume,
    build_telemetry_report,
    event_type_volume,
    frontend_load_errors,
)


def sample_events():
    return pd.DataFrame(
        [
            {
                "timestamp": "2026-11-03T23:30:00-02:00",
                "event_type": "api_request_completed",
                "tags": {"route_template": "/assets", "method": "GET", "status_code": 200, "duration_ms": 100},
            },
            {
                "timestamp": "2026-11-04T01:00:00Z",
                "event_type": "api_request_completed",
                "tags": {"route_template": "/assets", "method": "GET", "status_code": 500, "duration_ms": 300},
            },
            {
                "timestamp": "2026-11-04T02:00:00Z",
                "event_type": "frontend_data_load_completed",
                "tags": {"section": "inventory", "outcome": "error", "reason_code": "network_error", "duration_ms": 50},
            },
            {
                "timestamp": "2026-11-04T03:00:00Z",
                "event_type": "frontend_data_load_completed",
                "tags": {"section": "inventory", "outcome": "error", "duration_ms": 75},
            },
            {
                "timestamp": "2026-11-04T04:00:00Z",
                "event_type": "frontend_data_load_completed",
                "tags": {"section": "inventory", "outcome": "ready", "duration_ms": 20},
            },
        ]
    )


def test_api_volume_and_latency_are_grouped_by_utc_date_and_route():
    events = sample_events()

    assert api_request_volume(events) == [
        {"date": "2026-11-04", "route_template": "/assets", "method": "GET", "request_count": 2}
    ]
    assert api_request_latency(events) == [
        {
            "date": "2026-11-04",
            "route_template": "/assets",
            "request_count": 2,
            "mean_duration_ms": 200.0,
            "max_duration_ms": 300,
        }
    ]


def test_frontend_errors_are_grouped_by_section_and_reason():
    assert frontend_load_errors(sample_events()) == [
        {"date": "2026-11-04", "section": "inventory", "reason_code": "network_error", "error_count": 1},
        {"date": "2026-11-04", "section": "inventory", "reason_code": "unspecified", "error_count": 1},
    ]


def test_api_server_error_rate_uses_5xx_status_codes():
    assert api_request_server_errors(sample_events()) == [
        {
            "date": "2026-11-04",
            "route_template": "/assets",
            "request_count": 2,
            "server_error_count": 1,
            "server_error_rate": 0.5,
        }
    ]


def test_event_type_volume_counts_per_utc_day():
    assert event_type_volume(sample_events()) == [
        {"date": "2026-11-04", "event_type": "api_request_completed", "event_count": 2},
        {"date": "2026-11-04", "event_type": "frontend_data_load_completed", "event_count": 3},
    ]


def test_metrics_are_deterministic_and_do_not_mutate_input():
    events = sample_events()
    original = events.copy(deep=True)

    first = build_telemetry_report(events)
    second = build_telemetry_report(events)

    assert first == second
    pd.testing.assert_frame_equal(events, original)


def test_empty_events_return_empty_serializable_metrics():
    events = pd.DataFrame(columns=["timestamp", "event_type", "tags"])

    report = build_telemetry_report(events)

    assert report == {
        "event_type_volume": [],
        "api_request_volume": [],
        "api_request_server_errors": [],
        "api_request_latency": [],
        "frontend_load_errors": [],
    }
