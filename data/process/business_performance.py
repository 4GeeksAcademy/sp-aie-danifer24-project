"""Reusable business KPI transformations for the weekly reporting flow."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


EXPECTED_CURRENCY = {"valencia": "EUR", "miami": "USD"}
PROGRAMME_IDS = {"ventas-b2b", "liderazgo-basico", "onboarding-soporte"}
EVENT_TYPES = {
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "kit_cost_variance_detected",
}


def validate_and_aggregate(
    records: list[dict[str, Any]], week_start: date
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Validate source rows and aggregate accepted business events.

    Invalid records are rejected independently so one malformed event does not
    discard otherwise usable data. Repeated event IDs are counted once.
    """
    accepted = 0
    rejected = 0
    duplicates = 0
    seen_ids: set[str] = set()
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for record in records:
        event_id = str(record.get("event_id") or "")
        if not event_id:
            rejected += 1
            continue
        if event_id in seen_ids:
            duplicates += 1
            continue
        seen_ids.add(event_id)

        try:
            event_type = record["event_type"]
            tags = record["tags"]
            timestamp = record["timestamp"]
            if not isinstance(tags, dict) or event_type not in EVENT_TYPES:
                raise ValueError("invalid event payload")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if not isinstance(timestamp, datetime):
                raise ValueError("invalid timestamp")
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp.astimezone(timezone.utc).date().isocalendar()[:2] != week_start.isocalendar()[:2]:
                raise ValueError("event outside requested ISO week")

            office = tags["office"]
            programme_id = tags["programme_id"]
            currency = tags["currency"]
            if office not in EXPECTED_CURRENCY or programme_id not in PROGRAMME_IDS:
                raise ValueError("invalid reporting dimensions")
            if currency != EXPECTED_CURRENCY[office]:
                raise ValueError("currency does not match office")

            # Validate and calculate the event contribution before mutating an
            # aggregate, so a malformed record cannot partially affect output.
            delta = Decimal("0")
            counter = None
            if event_type == "inbound_order_created":
                delta = Decimal(str(tags["unit_cost"]))
                quantity = tags["quantity"]
                if (
                    not delta.is_finite()
                    or delta < 0
                    or not isinstance(quantity, int)
                    or isinstance(quantity, bool)
                    or quantity < 1
                ):
                    raise ValueError("invalid inbound cost or quantity")
                delta *= quantity
            elif event_type == "outbound_order_created":
                counter = "kits_delivered_count"
            elif event_type == "stock_threshold_triggered":
                counter = "shortage_events_count"
            elif event_type == "kit_cost_variance_detected":
                counter = "cost_variance_events_count"

            key = (office, programme_id)
            metrics = grouped.setdefault(
                key,
                {
                    "office": office,
                    "programme_id": programme_id,
                    "total_material_cost": Decimal("0"),
                    "kits_delivered_count": 0,
                    "shortage_events_count": 0,
                    "cost_variance_events_count": 0,
                    "currency": currency,
                },
            )
            metrics["total_material_cost"] += delta
            if counter:
                metrics[counter] += 1
            accepted += 1
        except (KeyError, TypeError, ValueError, InvalidOperation):
            rejected += 1

    rows = []
    for (office, programme_id), metrics in sorted(grouped.items()):
        rows.append(
            {
                **metrics,
                "total_material_cost": metrics["total_material_cost"].quantize(Decimal("0.01")),
                "week_start": week_start,
            }
        )
    return rows, {"processed_records": len(records), "accepted_records": accepted, "rejected_records": rejected, "duplicate_records": duplicates}