"""Read-only, typed support-agent tool backed by the incidents repository."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from services.api.database import get_database
from services.api.models import IncidentBranch, IncidentCategory, IncidentOrigin, IncidentStatus
from services.api.services.incidents import get_incident, list_incidents

INCIDENT_TOOL_TIMEOUT_SECONDS = 5
INCIDENT_TOOL_TIMEOUT_MESSAGE = (
    "No pude confirmar el estado de ese ticket ahora mismo."
)
INCIDENT_FILTER_REQUIRED_MESSAGE = (
    "Indica un identificador de ticket o al menos un filtro para consultar incidencias."
)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="incident-read-tool")


class IncidentLookupInput(BaseModel):
    """Tool input: lookup a ticket by ID or filter incidents by exposed API fields."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: int | None = Field(default=None, gt=0)
    status: IncidentStatus | None = None
    category: IncidentCategory | None = None
    origin: IncidentOrigin | None = None
    branch: IncidentBranch | None = None


class IncidentToolOutcome(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


class IncidentRecord(BaseModel):
    """Typed read-only projection of the incident API response fields."""

    id: int
    title: str
    description: str
    status: IncidentStatus
    category: IncidentCategory
    origin: IncidentOrigin
    branch: IncidentBranch
    created_at: datetime
    updated_at: datetime


class IncidentLookupOutput(BaseModel):
    outcome: IncidentToolOutcome
    incidents: list[IncidentRecord] = Field(default_factory=list)
    message: str | None = None


def _query_repository(request: IncidentLookupInput) -> IncidentLookupOutput:
    # This tool is in-process: it uses the same TinyDB table/repository as the API,
    # so JWT enforcement is applied at the API boundary and is not bypassed by HTTP.
    database = get_database()
    try:
        table = database.table("incidents")
        if request.ticket_id is not None:
            record = get_incident(table, request.ticket_id)
            raw_records = [record] if record is not None else []
        else:
            raw_records = list_incidents(
                table,
                status=request.status,
                category=request.category,
                origin=request.origin,
                branch=request.branch,
            )
        records = [IncidentRecord.model_validate(record) for record in raw_records]
        if not records:
            return IncidentLookupOutput(
                outcome=IncidentToolOutcome.NOT_FOUND,
                message=INCIDENT_TOOL_TIMEOUT_MESSAGE,
            )
        return IncidentLookupOutput(outcome=IncidentToolOutcome.FOUND, incidents=records)
    finally:
        database.close()


def lookup_incidents(request: IncidentLookupInput) -> IncidentLookupOutput:
    """Execute only a repository read; return an honest outcome on timeout/errors."""
    if request.ticket_id is None and not any(
        (request.status, request.category, request.origin, request.branch)
    ):
        return IncidentLookupOutput(
            outcome=IncidentToolOutcome.ERROR,
            message=INCIDENT_FILTER_REQUIRED_MESSAGE,
        )
    try:
        future = _executor.submit(_query_repository, request)
        return future.result(timeout=INCIDENT_TOOL_TIMEOUT_SECONDS)
    except FutureTimeout:
        return IncidentLookupOutput(
            outcome=IncidentToolOutcome.ERROR,
            message=INCIDENT_TOOL_TIMEOUT_MESSAGE,
        )
    except Exception:
        return IncidentLookupOutput(
            outcome=IncidentToolOutcome.ERROR,
            message=INCIDENT_TOOL_TIMEOUT_MESSAGE,
        )
