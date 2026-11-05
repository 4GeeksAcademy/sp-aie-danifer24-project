import json
from datetime import date, datetime, timezone
from pathlib import Path

from data.process.business_performance import validate_and_aggregate


SAMPLE_PATH = Path(__file__).resolve().parents[2] / "raw" / "business_performance_sample.json"


def test_sample_input_aggregates_business_kpis():
    records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    rows, counts = validate_and_aggregate(records, date(2026, 11, 2))

    assert rows == [
        {
            "office": "valencia",
            "programme_id": "ventas-b2b",
            "total_material_cost": 50,
            "kits_delivered_count": 1,
            "shortage_events_count": 0,
            "cost_variance_events_count": 0,
            "currency": "EUR",
            "week_start": date(2026, 11, 2),
        }
    ]
    assert counts == {
        "processed_records": 2,
        "accepted_records": 2,
        "rejected_records": 0,
        "duplicate_records": 0,
    }


def test_invalid_rows_are_rejected_individually_and_duplicates_ignored():
    valid = {
        "event_id": "evt-1",
        "event_type": "outbound_order_created",
        "timestamp": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "tags": {"office": "miami", "programme_id": "liderazgo-basico", "currency": "USD"},
    }
    invalid = {**valid, "event_id": "evt-2", "tags": {**valid["tags"], "currency": "EUR"}}

    rows, counts = validate_and_aggregate([valid, invalid, valid], date(2026, 11, 2))

    assert rows[0]["kits_delivered_count"] == 1
    assert counts == {
        "processed_records": 3,
        "accepted_records": 1,
        "rejected_records": 1,
        "duplicate_records": 1,
    }


def test_empty_week_returns_empty_partition():
    rows, counts = validate_and_aggregate([], date(2026, 11, 2))

    assert rows == []
    assert counts["processed_records"] == 0


def test_malformed_inbound_event_does_not_create_or_partially_update_row():
    records = [
        {
            "event_id": "invalid-inbound",
            "event_type": "inbound_order_created",
            "timestamp": datetime(2026, 11, 2, tzinfo=timezone.utc),
            "tags": {
                "office": "valencia",
                "programme_id": "ventas-b2b",
                "currency": "EUR",
                "unit_cost": 10,
            },
        },
        {
            "event_id": "valid-outbound",
            "event_type": "outbound_order_created",
            "timestamp": datetime(2026, 11, 2, tzinfo=timezone.utc),
            "tags": {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR"},
        },
    ]

    rows, counts = validate_and_aggregate(records, date(2026, 11, 2))

    assert len(rows) == 1
    assert rows[0]["total_material_cost"] == 0
    assert rows[0]["kits_delivered_count"] == 1
    assert counts["rejected_records"] == 1
    assert counts["accepted_records"] == 1


def test_non_finite_inbound_cost_is_rejected():
    record = {
        "event_id": "non-finite-cost",
        "event_type": "inbound_order_created",
        "timestamp": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "tags": {
            "office": "valencia",
            "programme_id": "ventas-b2b",
            "currency": "EUR",
            "unit_cost": "Infinity",
            "quantity": 1,
        },
    }

    rows, counts = validate_and_aggregate([record], date(2026, 11, 2))

    assert rows == []
    assert counts["rejected_records"] == 1


def test_week_start_must_be_monday():
    import pytest

    from data.pipelines.pipeline import resolve_week

    with pytest.raises(ValueError, match="ISO week Monday"):
        resolve_week.fn(date(2026, 11, 3))


def test_pipeline_tasks_configure_retries_and_one_hour_transform_cache():
    from datetime import timedelta

    from data.pipelines.pipeline import (
        extract_events,
        load_week_partition,
        mark_pipeline_run_failed,
        start_pipeline_run,
        transform_business_kpis,
    )

    assert start_pipeline_run.retries == 1
    assert start_pipeline_run.retry_delay_seconds == 1
    assert extract_events.retries == 3
    assert extract_events.retry_delay_seconds == [1, 5, 15]
    assert load_week_partition.retries == 3
    assert load_week_partition.retry_delay_seconds == [1, 5, 15]
    assert mark_pipeline_run_failed.retries == 2
    assert mark_pipeline_run_failed.retry_delay_seconds == [1, 5]
    assert transform_business_kpis.cache_key_fn is not None
    assert transform_business_kpis.cache_expiration == timedelta(hours=1)
    assert extract_events.fn.__name__ == "extract_events"
    assert load_week_partition.fn.__name__ == "load_week_partition"


def test_explicitly_captured_failed_task_state_reraises_original_exception():
    import pytest
    from prefect.states import Failed

    from data.pipelines.pipeline import _result_or_raise

    error = RuntimeError("reporting database unavailable")
    failed_state = Failed(data=error)

    with pytest.raises(RuntimeError, match="reporting database unavailable"):
        _result_or_raise(failed_state)


def test_extraction_requires_explicit_read_only_guard(monkeypatch):
    import pytest

    from data.pipelines.pipeline import extract_events

    monkeypatch.delenv("TELEMETRY_DATABASE_READ_ONLY", raising=False)
    with pytest.raises(RuntimeError, match="TELEMETRY_DATABASE_READ_ONLY=true"):
        extract_events.fn(date(2026, 11, 2))
