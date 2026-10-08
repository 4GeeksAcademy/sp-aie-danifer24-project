"""CRUD and aggregate endpoints for centralized incidents."""

from collections import Counter
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pydantic import ValidationError
from tinydb import Query as TinyQuery
from tinydb.table import Table

from services.api.dependencies import RequestTables
from services.api.models import (
    IncidentBranch,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentResponse,
    IncidentStatus,
    IncidentStatusUpdate,
)
from services.api.security import get_current_user


router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(get_current_user)],
)


def get_incidents_table(tables: RequestTables) -> Table:
    return tables[4]


IncidentsTable = Annotated[Table, Depends(get_incidents_table)]
IncidentId = Annotated[int, Path(gt=0)]


STATUS_TRANSITIONS = {
    IncidentStatus.OPEN: {IncidentStatus.IN_PROGRESS, IncidentStatus.DISCARDED},
    IncidentStatus.IN_PROGRESS: {IncidentStatus.RESOLVED, IncidentStatus.DISCARDED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.DISCARDED: set(),
}


ERROR_MESSAGES = {
    "title": "El título es obligatorio y no puede estar vacío.",
    "description": "La descripción es obligatoria y no puede estar vacía.",
    "category": "La categoría no es válida.",
    "status": "El estado no es válido.",
    "origin": "El origen no es válido.",
    "branch": "La sede no es válida.",
}


def validation_errors(error: ValidationError) -> list[dict[str, str]]:
    errors = []
    for item in error.errors():
        field = str(item["loc"][-1]) if item["loc"] else "body"
        errors.append(
            {
                "field": field,
                "message": ERROR_MESSAGES.get(field, "El valor enviado no es válido."),
            }
        )
    return errors


def incident_response(document, doc_id: int | None = None) -> IncidentResponse:
    payload = dict(document)
    payload["id"] = doc_id if doc_id is not None else payload.get("id")
    return IncidentResponse.model_validate(payload)


def find_incident(table: Table, incident_id: int):
    document = table.get(doc_id=incident_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No se encontró la incidencia solicitada.")
    return document


@router.post("", response_model=IncidentResponse, status_code=201)
def create_incident(*, payload: Any = Body(...), table: IncidentsTable):
    try:
        request = IncidentCreate.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=400,
            detail={"message": "La incidencia contiene datos no válidos.", "errors": validation_errors(error)},
        ) from error

    now = datetime.now(timezone.utc).isoformat()
    now_payload = request.model_dump(mode="json")
    now_payload.update(created_at=now, updated_at=now)
    incident_id = table.insert(now_payload)
    return incident_response({**now_payload, "id": incident_id})


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    table: IncidentsTable,
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: IncidentBranch | None = None,
    category: IncidentCategory | None = None,
):
    query = TinyQuery()
    filters = query.noop()
    for field, value in (
        ("status", status),
        ("origin", origin),
        ("branch", branch),
        ("category", category),
    ):
        if value is not None:
            filters &= query[field] == value.value
    return [incident_response(document, document.doc_id) for document in table.search(filters)]


@router.get("/summary")
def incidents_summary(table: IncidentsTable):
    documents = table.all()

    def counts(field: str, allowed_values) -> dict[str, int]:
        result = {value.value: 0 for value in allowed_values}
        result.update(Counter(item.get(field) for item in documents))
        result.pop(None, None)
        return result

    return {
        "total": len(documents),
        "by_status": counts("status", IncidentStatus),
        "by_category": counts("category", IncidentCategory),
        "by_origin": counts("origin", IncidentOrigin),
        "by_branch": counts("branch", IncidentBranch),
    }


@router.get("/{id}", response_model=IncidentResponse)
def retrieve_incident(id: IncidentId, table: IncidentsTable):
    document = find_incident(table, id)
    return incident_response(document, document.doc_id)


@router.patch("/{id}/status", response_model=IncidentResponse)
def update_incident_status(
    id: IncidentId, request: IncidentStatusUpdate, table: IncidentsTable
):
    document = find_incident(table, id)
    current_status = IncidentStatus(document["status"])
    if request.status not in STATUS_TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    f"No se puede cambiar el estado de '{current_status.value}' "
                    f"a '{request.status.value}'."
                ),
                "field": "status",
            },
        )

    table.update(
        {"status": request.status.value, "updated_at": datetime.now(timezone.utc).isoformat()},
        doc_ids=[id],
    )
    updated = find_incident(table, id)
    return incident_response(updated, updated.doc_id)
