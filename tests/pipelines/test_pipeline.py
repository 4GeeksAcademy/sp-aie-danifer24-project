from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data.pipelines.pipeline import transform_business_kpis


WEEK_START = date(2026, 11, 2)
EVENT_TIME = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def telemetry_event(event_id: str, event_type: str, **tags: object) -> dict:
    """Build an in-memory event using the telemetry_events record shape."""
    base_tags = {
        "office": "valencia",
        "programme_id": "ventas-b2b",
        "currency": "EUR",
    }
    return {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": EVENT_TIME,
        "tags": {**base_tags, **tags},
    }


def test_transformation_calculates_material_cost_from_inbound_orders():
    result = transform_business_kpis.fn(
        [
            telemetry_event(
                "inbound-1",
                "inbound_order_created",
                unit_cost="12.50",
                quantity=2,
            ),
            telemetry_event(
                "inbound-2",
                "inbound_order_created",
                unit_cost="3.25",
                quantity=1,
            ),
        ],
        WEEK_START,
    )

    assert result["rows"][0]["total_material_cost"] == Decimal("28.25")


def test_transformation_counts_delivered_kits_from_outbound_events():
    result = transform_business_kpis.fn(
        [
            telemetry_event("outbound-1", "outbound_order_created"),
            telemetry_event("outbound-2", "outbound_order_created"),
            telemetry_event("outbound-3", "outbound_order_created"),
        ],
        WEEK_START,
    )

    assert result["rows"][0]["kits_delivered_count"] == 3


def test_transformation_counts_shortage_events():
    result = transform_business_kpis.fn(
        [
            telemetry_event("shortage-1", "stock_threshold_triggered"),
            telemetry_event("shortage-2", "stock_threshold_triggered"),
        ],
        WEEK_START,
    )

    assert result["rows"][0]["shortage_events_count"] == 2


def test_transformation_counts_cost_variance_events():
    result = transform_business_kpis.fn(
        [
            telemetry_event("variance-1", "kit_cost_variance_detected"),
        ],
        WEEK_START,
    )

    assert result["rows"][0]["cost_variance_events_count"] == 1


def test_transformation_rejects_malformed_event_without_partial_kpi_update():
    malformed = telemetry_event(
        "bad-inbound",
        "inbound_order_created",
        unit_cost=None,
        quantity=2,
    )
    valid = telemetry_event("outbound-1", "outbound_order_created")

    result = transform_business_kpis.fn([malformed, valid], WEEK_START)

    assert result["rows"] == [
        {
            "office": "valencia",
            "programme_id": "ventas-b2b",
            "total_material_cost": Decimal("0.00"),
            "kits_delivered_count": 1,
            "shortage_events_count": 0,
            "cost_variance_events_count": 0,
            "currency": "EUR",
            "week_start": WEEK_START,
        }
    ]
    assert result["processed_records"] == 2
    assert result["accepted_records"] == 1
    assert result["rejected_records"] == 1
    assert result["duplicate_records"] == 0


def test_transformation_rejects_non_mapping_tags():
    malformed = {
        "event_id": "bad-tags",
        "event_type": "outbound_order_created",
        "timestamp": EVENT_TIME,
        "tags": None,
    }

    result = transform_business_kpis.fn([malformed], WEEK_START)

    assert result["rows"] == []
    assert result["rejected_records"] == 1
    assert result["accepted_records"] == 0


@pytest.mark.parametrize(
    ("office", "currency"),
    [("valencia", "EUR"), ("miami", "USD")],
)
def test_transformation_preserves_local_currency(office: str, currency: str):
    event = telemetry_event(
        "outbound-1",
        "outbound_order_created",
        office=office,
        currency=currency,
    )

    result = transform_business_kpis.fn([event], WEEK_START)

    assert result["rows"][0]["currency"] == currency
