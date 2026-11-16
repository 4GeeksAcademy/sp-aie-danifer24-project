"""Read-only query helpers shared by the incidents API and support-agent tool."""

from typing import Any

from tinydb import Query
from tinydb.table import Table

from services.api.models import IncidentBranch, IncidentCategory, IncidentOrigin, IncidentStatus


def list_incidents(
    table: Table,
    *,
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: IncidentBranch | None = None,
    category: IncidentCategory | None = None,
) -> list[dict[str, Any]]:
    """Read incidents applying the same filters exposed by GET /api/incidents."""
    query = Query()
    filters = query.noop()
    for field, value in (
        ("status", status),
        ("origin", origin),
        ("branch", branch),
        ("category", category),
    ):
        if value is not None:
            filters &= query[field] == value.value
    return [dict(document, id=document.doc_id) for document in table.search(filters)]


def get_incident(table: Table, incident_id: int) -> dict[str, Any] | None:
    """Read one incident by its TinyDB document ID, or return None if absent."""
    document = table.get(doc_id=incident_id)
    if document is None:
        return None
    return dict(document, id=document.doc_id)
