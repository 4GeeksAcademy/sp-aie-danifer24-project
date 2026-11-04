from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from services.api.models import TelemetryEventRecord
from services.api.routes.telemetry import receive_events
from services.api.schemas import TelemetryBatch


VALID_EVENT = {
    "eventId": "4e8dc421-8c46-4be4-9f88-a8a911f90d39",
    "timestamp": "2026-11-04T12:00:00Z",
    "sessionId": None,
    "userId": None,
    "event_type": "login_attempted",
    "schemaVersion": "1.0.0",
    "requestId": "278b8b8d-3139-41ca-8132-e18d9e8615d4",
    "properties": {"source": "backoffice"},
}


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_mixed_batch_persists_valid_event_and_rejects_invalid_one():
    engine, session = make_session()
    invalid_event = {**VALID_EVENT, "eventId": "not-a-uuid"}
    try:
        receipt = receive_events(TelemetryBatch(events=[VALID_EVENT, invalid_event]), session)
        stored = session.exec(select(TelemetryEventRecord)).all()

        assert receipt.model_dump() == {"received": 2, "stored": 1, "rejected": 1}
        assert len(stored) == 1
        assert stored[0].event_id == VALID_EVENT["eventId"]
        assert stored[0].event_type == "login_attempted"
        assert stored[0].service == "backoffice"
        assert stored[0].tags == {"source": "backoffice"}
        assert stored[0].timestamp.replace(tzinfo=timezone.utc) == datetime(
            2026, 11, 4, 12, 0, tzinfo=timezone.utc
        )
    finally:
        session.close()
        engine.dispose()


def test_duplicate_event_id_is_not_inserted_twice():
    engine, session = make_session()
    try:
        first = receive_events(TelemetryBatch(events=[VALID_EVENT]), session)
        second = receive_events(TelemetryBatch(events=[VALID_EVENT]), session)

        assert first.model_dump() == {"received": 1, "stored": 1, "rejected": 0}
        assert second.model_dump() == {"received": 1, "stored": 0, "rejected": 0}
        assert len(session.exec(select(TelemetryEventRecord)).all()) == 1
    finally:
        session.close()
        engine.dispose()


def test_event_with_non_allowlisted_property_is_rejected():
    engine, session = make_session()
    invalid_event = {
        **VALID_EVENT,
        "properties": {"source": "backoffice", "email": "person@example.test"},
    }
    try:
        receipt = receive_events(TelemetryBatch(events=[invalid_event]), session)

        assert receipt.model_dump() == {"received": 1, "stored": 0, "rejected": 1}
        assert len(session.exec(select(TelemetryEventRecord)).all()) == 0
    finally:
        session.close()
        engine.dispose()
