"""Telemetry ingestion with per-event contract validation and bulk persistence."""

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from services.api.database import get_db
from services.api.models import TelemetryEventRecord
from services.api.schemas import TelemetryBatch, TelemetryEvent, TelemetryReceipt
from services.api.telemetry_contract import validate_telemetry_contract


load_dotenv(Path(__file__).resolve().parents[3] / ".env")
TELEMETRY_ENDPOINT = os.environ.get("TELEMETRY_ENDPOINT")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger("uvicorn.error.telemetry")


@router.post("/events", response_model=TelemetryReceipt)
def receive_events(batch: TelemetryBatch, session: Session = Depends(get_db)) -> TelemetryReceipt:
    records: list[dict] = []
    rejected = 0
    for raw_event in batch.events:
        try:
            event = TelemetryEvent.model_validate(raw_event)
            validate_telemetry_contract(event.model_dump(mode="json"))
        except (ValidationError, ValueError, TypeError):
            rejected += 1
            continue

        records.append({
            "event_id": event.eventId,
            "event_type": event.event_type,
            "timestamp": datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")),
            "service": "backoffice",
            "tags": event.properties,
            "session_id": event.sessionId,
            "user_id": event.userId,
            "schema_version": event.schemaVersion,
            "request_id": event.requestId,
        })

    stored = 0
    if records:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            statement = postgresql_insert(TelemetryEventRecord).values(records).on_conflict_do_nothing(
                index_elements=[TelemetryEventRecord.event_id]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(TelemetryEventRecord).values(records).on_conflict_do_nothing(
                index_elements=[TelemetryEventRecord.event_id]
            )
        else:
            raise RuntimeError(f"Unsupported telemetry database dialect: {dialect}")

        try:
            result = session.execute(statement)
            session.commit()
        except Exception:
            session.rollback()
            raise
        stored = max(result.rowcount or 0, 0)

    logger.info(
        "Telemetry batch processed: received=%d stored=%d rejected=%d",
        len(batch.events), stored, rejected,
    )
    return TelemetryReceipt(received=len(batch.events), stored=stored, rejected=rejected)