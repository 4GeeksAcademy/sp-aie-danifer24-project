"""
Incidents Manager MCP tools.

All tools read from and write to the same TinyDB-backed incidents store that
the FastAPI Incidents Manager uses.  Status transitions go through the
lifecycle endpoint logic (``PATCH /api/incidents/{id}/status``), enforcing
the same state machine:

    OPEN → IN_PROGRESS | DISCARDED
    IN_PROGRESS → RESOLVED | DISCARDED
    RESOLVED → ∅
    DISCARDED → ∅
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinydb import Query
from tinydb.table import Table

# Importing services.api.database triggers load_dotenv(), which may set
# SUPPLIERS_DB_PATH to the Docker path.  We handle the local- vs Docker-path
# resolution in _get_database() ourselves.
from services.api.database import get_database as _api_get_database
from services.api.database import DEFAULT_DATABASE_PATH as _API_DEFAULT_DB_PATH
from services.api.models import (
    IncidentBranch,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentStatus,
    IncidentStatusUpdate,
)

# ── Timeout (seconds) ────────────────────────────────────────────────────
INCIDENT_TOOL_TIMEOUT_SECONDS = 5
TIMEOUT_MESSAGE = "No pude completar la operación sobre el ticket ahora mismo."


# ---------------------------------------------------------------------------
# Local DB path resolution (for running outside Docker)
# ---------------------------------------------------------------------------
def _get_database():
    """Return a TinyDB database instance.

    Tries, in order:
        1. Repo-root ``data/suppliers.json`` — the canonical file that all
           services share.
        2. ``SUPPLIERS_DB_PATH`` env var (the Docker / container path) —
           checked second because on Windows the Docker path
           ``/app/data/suppliers.json`` may resolve to an *empty* file that
           ``load_dotenv()`` from the API module creates via
           ``path.parent.mkdir()``.
        3. The API's default path logic (via ``services.api.database.get_database``).
    """
    # ── 1. Repo-root data/suppliers.json ──────────────────────────────────
    repo_root = Path(__file__).resolve().parents[3]  # incidents.py -> repo root
    local_path = (repo_root / "data" / "suppliers.json").resolve()
    if local_path.exists() and local_path.stat().st_size > 0:
        from tinydb import TinyDB
        return TinyDB(local_path)

    # ── 2. SUPPLIERS_DB_PATH (Docker path) ────────────────────────────────
    import os as _os
    db_path = _os.environ.get("SUPPLIERS_DB_PATH", "")
    if db_path and Path(db_path).exists():
        p = Path(db_path)
        if p.stat().st_size > 0:
            from tinydb import TinyDB
            return TinyDB(p)

    # ── 3. API default (last resort) ──────────────────────────────────────
    return _api_get_database()

# ── Valid status transitions ─────────────────────────────────────────────
STATUS_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.IN_PROGRESS, IncidentStatus.DISCARDED},
    IncidentStatus.IN_PROGRESS: {IncidentStatus.RESOLVED, IncidentStatus.DISCARDED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.DISCARDED: set(),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get_table() -> Table:
    db = _get_database()
    return db.table("incidents")


def _get_incident(table: Table, incident_id: int) -> dict[str, Any] | None:
    doc = table.get(doc_id=incident_id)
    if doc is None:
        return None
    return {**doc, "id": doc.doc_id}


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalise datetime objects to ISO strings for JSON transport."""
    result: dict[str, Any] = {}
    for key, value in doc.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Tool implementations (called by FastMCP decorated functions in server.py)
# ---------------------------------------------------------------------------

def lookup_incident(incident_id: int) -> dict[str, Any]:
    """Retrieve a single incident by its TinyDB document ID.

    Parameters
    ----------
    incident_id : int
        The numeric ID of the incident (> 0).

    Returns
    -------
    dict
        Incident record with fields: id, title, description, status,
        category, origin, branch, created_at, updated_at.
        If not found: {"outcome": "not_found", "message": "..."}.
    """
    table = _get_table()
    record = _get_incident(table, incident_id)
    if record is None:
        return {
            "outcome": "not_found",
            "message": "No se encontró la incidencia solicitada.",
        }
    return {"outcome": "found", "incident": _serialize(record)}


def list_incidents_tool(
    status: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
) -> list[dict[str, Any]]:
    """List incidents with optional filters.

    Parameters
    ----------
    status : str, optional
        Filter by status. One of: open, in_progress, resolved, discarded.
    category : str, optional
        Filter by category. One of: technical_failure, process_error,
        client_complaint, candidate_issue, staff_issue, sla_breach,
        data_quality, other.
    origin : str, optional
        Filter by origin. One of: customer, branch, internal.
    branch : str, optional
        Filter by branch. One of: central, valencia_operations,
        miami_office, remote.

    Returns
    -------
    list[dict]
        Array of matching incident records.
    """
    table = _get_table()
    q = Query()
    filters = q.noop()

    enum_map: dict[str, tuple[type, str]] = {
        "status": (IncidentStatus, "status"),
        "category": (IncidentCategory, "category"),
        "origin": (IncidentOrigin, "origin"),
        "branch": (IncidentBranch, "branch"),
    }
    for param_name, raw_value in (
        ("status", status),
        ("category", category),
        ("origin", origin),
        ("branch", branch),
    ):
        if raw_value is not None:
            filters &= q[param_name] == raw_value

    documents = table.search(filters)
    return [
        _serialize({**doc, "id": doc.doc_id}) for doc in documents
    ]


def create_incident_tool(
    title: str,
    description: str,
    category: str,
    status: str,
    origin: str,
    branch: str,
) -> dict[str, Any]:
    """Create a new incident in the Incidents Manager.

    Parameters
    ----------
    title : str
        Incident title (non‑empty).
    description : str
        Detailed description (non‑empty).
    category : str
        One of: technical_failure, process_error, client_complaint,
        candidate_issue, staff_issue, sla_breach, data_quality, other.
    status : str
        Initial status. One of: open, in_progress, resolved, discarded.
    origin : str
        One of: customer, branch, internal.
    branch : str
        One of: central, valencia_operations, miami_office, remote.

    Returns
    -------
    dict
        Created incident record with id, title, description, status,
        category, origin, branch, created_at, updated_at.
    """
    # Validate enums ── let the API's own Pydantic model do the heavy lifting.
    payload = IncidentCreate(
        title=title,
        description=description,
        category=IncidentCategory(category),
        status=IncidentStatus(status),
        origin=IncidentOrigin(origin),
        branch=IncidentBranch(branch),
    )

    now = datetime.now(timezone.utc)
    record: dict[str, Any] = {
        **payload.model_dump(mode="json"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    record.pop("id", None)

    table = _get_table()
    doc_id = table.insert(record)
    record["id"] = doc_id
    return _serialize(record)


def update_incident_status_tool(
    incident_id: int,
    new_status: str,
) -> dict[str, Any]:
    """Transition an incident to a new status via the lifecycle endpoint.

    The valid transitions are:
      - open        → in_progress | discarded
      - in_progress → resolved    | discarded
      - resolved    → (none)
      - discarded   → (none)

    Parameters
    ----------
    incident_id : int
        The numeric ID of the incident (> 0).
    new_status : str
        Target status: open, in_progress, resolved, or discarded.

    Returns
    -------
    dict
        Updated incident record, or an error dict with ``outcome`` and
        ``message`` fields.
    """
    table = _get_table()
    record = _get_incident(table, incident_id)
    if record is None:
        return {
            "outcome": "not_found",
            "message": "No se encontró la incidencia solicitada.",
        }

    current = IncidentStatus(record["status"])
    target = IncidentStatus(new_status)

    allowed = STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        return {
            "outcome": "error",
            "message": (
                f"No se puede cambiar el estado de '{current.value}' "
                f"a '{target.value}'. Transiciones permitidas desde "
                f"'{current.value}': {[s.value for s in allowed] or ['(ninguna)']}."
            ),
        }

    now = datetime.now(timezone.utc).isoformat()
    table.update(
        {"status": target.value, "updated_at": now},
        doc_ids=[incident_id],
    )
    updated = _get_incident(table, incident_id)
    return _serialize(updated)


def delete_incident_tool(incident_id: int) -> dict[str, Any]:
    """Permanently remove an incident record (admin purpose).

    Parameters
    ----------
    incident_id : int
        The numeric ID of the incident (> 0).

    Returns
    -------
    dict
        Confirmation with ``outcome`` set to ``"deleted"``, or an
        error dict if the incident does not exist.
    """
    table = _get_table()
    record = _get_incident(table, incident_id)
    if record is None:
        return {
            "outcome": "not_found",
            "message": "No se encontró la incidencia solicitada.",
        }
    table.remove(doc_ids=[incident_id])
    return {"outcome": "deleted", "message": f"Incidencia {incident_id} eliminada."}