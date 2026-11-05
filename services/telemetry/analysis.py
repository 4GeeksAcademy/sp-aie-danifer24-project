"""Pure Pandas metrics for operational telemetry events.

The input DataFrame uses the persisted telemetry_events shape: ``timestamp``,
``event_type`` and ``tags``. These functions only transform their input and
return JSON-serializable records; database loading and HTTP serving belong to
separate layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlmodel import Session, select

from services.api.models import TelemetryEventRecord


API_REQUEST_EVENT = "api_request_completed"
FRONTEND_LOAD_EVENT = "frontend_data_load_completed"
FRONTEND_UNHANDLED_ERROR_EVENT = "frontend_unhandled_error"
ERROR_RATE_EVENT_TYPES = (
    API_REQUEST_EVENT,
    FRONTEND_LOAD_EVENT,
    FRONTEND_UNHANDLED_ERROR_EVENT,
)


def _load_events(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    event_types: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Load only timestamp-bounded telemetry rows required by a metric."""
    statement = select(
        TelemetryEventRecord.timestamp,
        TelemetryEventRecord.event_type,
        TelemetryEventRecord.tags,
    ).where(
        TelemetryEventRecord.timestamp >= start_date,
        TelemetryEventRecord.timestamp < end_date,
    )
    if event_types is not None:
        statement = statement.where(TelemetryEventRecord.event_type.in_(event_types))
    rows = session.exec(statement).all()
    return pd.DataFrame.from_records(
        (row._mapping for row in rows),
        columns=["timestamp", "event_type", "tags"],
    )


def events_per_day(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Count persisted events by UTC day and event type within SQL date bounds."""
    return event_type_volume(_load_events(session, start_date, end_date))


def error_rate_by_type(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Calculate technical error rates for captured API and frontend events."""
    frame = _load_events(session, start_date, end_date, ERROR_RATE_EVENT_TYPES)
    if frame.empty:
        return []

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp", "event_type"])
    frame["date"] = frame["timestamp"].dt.date
    tags = pd.json_normalize(frame["tags"].map(lambda value: value if isinstance(value, dict) else {}))
    tags.index = frame.index
    frame = frame.join(tags, suffixes=("", "_tag"))
    frame["status_code"] = pd.to_numeric(
        frame.get("status_code", pd.Series(index=frame.index, dtype="object")),
        errors="coerce",
    )
    frame["is_error"] = (
        (frame["event_type"].eq(API_REQUEST_EVENT) & frame["status_code"].ge(500))
        | (frame["event_type"].eq(FRONTEND_LOAD_EVENT) & frame.get("outcome", pd.Series(index=frame.index, dtype="object")).eq("error"))
        | frame["event_type"].eq(FRONTEND_UNHANDLED_ERROR_EVENT)
    )
    grouped = (
        frame.groupby(["date", "event_type"], as_index=False)
        .agg(event_count=("event_type", "count"), error_count=("is_error", "sum"))
        .sort_values(["date", "event_type"])
    )
    grouped["error_rate"] = grouped["error_count"] / grouped["event_count"]
    return _records(grouped.set_index(["date", "event_type"]))


def _prepare_events(events: pd.DataFrame, event_type: str) -> pd.DataFrame:
    """Return a filtered copy with UTC datetime timestamps and normalized tags."""
    required = {"timestamp", "event_type", "tags"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Missing telemetry columns: {', '.join(sorted(missing))}")

    frame = events.loc[events["event_type"].eq(event_type)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    frame["date"] = frame["timestamp"].dt.date
    tags = pd.json_normalize(frame["tags"].map(lambda value: value if isinstance(value, dict) else {}))
    tags.index = frame.index
    return frame.join(tags, suffixes=("", "_tag"))


def _records(grouped: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a grouped result into JSON-safe dictionaries."""
    result = grouped.reset_index()
    if "date" in result.columns:
        result["date"] = result["date"].astype(str)
    return result.to_dict(orient="records")


def api_request_volume(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Count completed API requests per UTC day, route template, and method."""
    frame = _prepare_events(events, API_REQUEST_EVENT)
    frame["route_template"] = frame.get("route_template", pd.Series(index=frame.index, dtype="object"))
    frame["method"] = frame.get("method", pd.Series(index=frame.index, dtype="object"))
    frame = frame.dropna(subset=["route_template", "method"])
    grouped = (
        frame.groupby(["date", "route_template", "method"], as_index=False)
        .agg(request_count=("event_type", "count"))
        .sort_values(["date", "route_template", "method"])
    )
    return _records(grouped.set_index(["date", "route_template", "method"]))


def api_request_latency(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Report mean and maximum API response time per UTC day and route."""
    frame = _prepare_events(events, API_REQUEST_EVENT)
    frame["route_template"] = frame.get("route_template", pd.Series(index=frame.index, dtype="object"))
    frame["duration_ms"] = pd.to_numeric(frame.get("duration_ms"), errors="coerce")
    frame = frame.dropna(subset=["route_template", "duration_ms"])
    frame = frame.loc[frame["duration_ms"].ge(0)]
    grouped = (
        frame.groupby(["date", "route_template"], as_index=False)
        .agg(request_count=("duration_ms", "count"), mean_duration_ms=("duration_ms", "mean"), max_duration_ms=("duration_ms", "max"))
        .sort_values(["date", "route_template"])
    )
    return _records(grouped.set_index(["date", "route_template"]))


def api_request_server_errors(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Report 5xx counts and rates per UTC day and route template."""
    frame = _prepare_events(events, API_REQUEST_EVENT)
    frame["route_template"] = frame.get("route_template", pd.Series(index=frame.index, dtype="object"))
    frame["status_code"] = pd.to_numeric(frame.get("status_code"), errors="coerce")
    frame = frame.dropna(subset=["route_template", "status_code"])
    frame["is_server_error"] = frame["status_code"].ge(500)
    grouped = (
        frame.groupby(["date", "route_template"], as_index=False)
        .agg(
            request_count=("status_code", "count"),
            server_error_count=("is_server_error", "sum"),
        )
        .sort_values(["date", "route_template"])
    )
    grouped["server_error_rate"] = grouped["server_error_count"] / grouped["request_count"]
    return _records(grouped.set_index(["date", "route_template"]))


def frontend_load_errors(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Count failed frontend data loads per UTC day, section, and reason."""
    frame = _prepare_events(events, FRONTEND_LOAD_EVENT)
    frame["section"] = frame.get("section", pd.Series(index=frame.index, dtype="object"))
    frame["reason_code"] = frame.get("reason_code", pd.Series(index=frame.index, dtype="object"))
    frame = frame.loc[frame.get("outcome", pd.Series(index=frame.index, dtype="object")).eq("error")]
    frame = frame.dropna(subset=["section"])
    frame["reason_code"] = frame["reason_code"].fillna("unspecified")
    grouped = (
        frame.groupby(["date", "section", "reason_code"], as_index=False)
        .agg(error_count=("event_type", "count"))
        .sort_values(["date", "section", "reason_code"])
    )
    return _records(grouped.set_index(["date", "section", "reason_code"]))


def event_type_volume(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Count all valid telemetry events per UTC day and event type."""
    required = {"timestamp", "event_type"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Missing telemetry columns: {', '.join(sorted(missing))}")

    frame = events.loc[:, ["timestamp", "event_type"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp", "event_type"])
    frame["date"] = frame["timestamp"].dt.date
    grouped = (
        frame.groupby(["date", "event_type"], as_index=False)
        .agg(event_count=("event_type", "count"))
        .sort_values(["date", "event_type"])
    )
    return _records(grouped.set_index(["date", "event_type"]))


def build_telemetry_report(events: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Build the operational report from an already-loaded telemetry frame."""
    return {
        "event_type_volume": event_type_volume(events),
        "api_request_volume": api_request_volume(events),
        "api_request_server_errors": api_request_server_errors(events),
        "api_request_latency": api_request_latency(events),
        "frontend_load_errors": frontend_load_errors(events),
    }
