from datetime import datetime, timezone

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from services.api.models import IncidentCategory, IncidentOrigin, IncidentStatus
from services.api.services import incident_tool
from services.api.services.incident_tool import (
    INCIDENT_TOOL_TIMEOUT_MESSAGE,
    IncidentLookupInput,
    IncidentToolOutcome,
    lookup_incidents,
)


def incident_record(**overrides):
    return {
        "title": "Cannot access account",
        "description": "Login fails for the customer.",
        "status": "open",
        "category": "technical_failure",
        "origin": "customer",
        "branch": "central",
        "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
        **overrides,
    }


def test_lookup_reads_existing_incident_from_shared_tinydb_and_is_read_only(monkeypatch):
    database = TinyDB(storage=MemoryStorage)
    table = database.table("incidents")
    incident_id = table.insert(incident_record())
    monkeypatch.setattr(incident_tool, "get_database", lambda: database)

    result = lookup_incidents(IncidentLookupInput(ticket_id=incident_id))

    assert result.outcome is IncidentToolOutcome.FOUND
    record = result.incidents[0]
    assert record.id == incident_id
    assert record.status is IncidentStatus.OPEN
    assert record.category is IncidentCategory.TECHNICAL_FAILURE
    assert record.origin is IncidentOrigin.CUSTOMER
    assert table.get(doc_id=incident_id)["status"] == "open"
    assert len(table) == 1
    database.close()


def test_lookup_supports_filters_and_refuses_unbounded_incident_listing(monkeypatch):
    database = TinyDB(storage=MemoryStorage)
    table = database.table("incidents")
    matching_id = table.insert(incident_record())
    table.insert(incident_record(status="resolved", origin="internal"))
    monkeypatch.setattr(incident_tool, "get_database", lambda: database)

    result = lookup_incidents(
        IncidentLookupInput(status=IncidentStatus.OPEN, origin=IncidentOrigin.CUSTOMER)
    )
    unbounded = lookup_incidents(IncidentLookupInput())

    assert result.outcome is IncidentToolOutcome.FOUND
    assert [item.id for item in result.incidents] == [matching_id]
    assert unbounded.outcome is IncidentToolOutcome.ERROR
    assert "filtro" in unbounded.message
    database.close()


def test_lookup_returns_honest_fallback_for_missing_id_and_repository_error(monkeypatch):
    database = TinyDB(storage=MemoryStorage)
    monkeypatch.setattr(incident_tool, "get_database", lambda: database)
    missing = lookup_incidents(IncidentLookupInput(ticket_id=789))
    assert missing.outcome is IncidentToolOutcome.NOT_FOUND
    assert missing.message == INCIDENT_TOOL_TIMEOUT_MESSAGE

    database.close()
    monkeypatch.setattr(
        incident_tool, "_query_repository", lambda request: (_ for _ in ()).throw(OSError("secret"))
    )
    failed = lookup_incidents(IncidentLookupInput(ticket_id=789))
    assert failed.outcome is IncidentToolOutcome.ERROR
    assert failed.message == INCIDENT_TOOL_TIMEOUT_MESSAGE
    assert "secret" not in failed.message


def test_lookup_returns_honest_fallback_when_repository_times_out(monkeypatch):
    monkeypatch.setattr(incident_tool, "INCIDENT_TOOL_TIMEOUT_SECONDS", 0.01)

    def slow_query(request):
        import time

        time.sleep(0.05)
        return None

    monkeypatch.setattr(incident_tool, "_query_repository", slow_query)
    result = lookup_incidents(IncidentLookupInput(ticket_id=789))

    assert result.outcome is IncidentToolOutcome.ERROR
    assert result.message == INCIDENT_TOOL_TIMEOUT_MESSAGE
