"""Temporary telemetry receiver: validate envelopes, log metadata, never persist."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter

from services.api.schemas import TelemetryBatch, TelemetryReceipt


load_dotenv(Path(__file__).resolve().parents[3] / ".env")
TELEMETRY_ENDPOINT = os.environ.get("TELEMETRY_ENDPOINT")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
logger = logging.getLogger("uvicorn.error.telemetry")


@router.post("/events", response_model=TelemetryReceipt)
def receive_events(batch: TelemetryBatch) -> TelemetryReceipt:
    logger.info("Telemetry batch received: count=%d", len(batch.events))
    for event in batch.events:
        logger.info("Telemetry event received: event_type=%s", event.event_type)
    return TelemetryReceipt(received=len(batch.events))