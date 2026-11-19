"""
Incidents Manager MCP tools.

All incident operations are delegated to the authenticated FastAPI Incidents
Manager API. Status transitions use ``PATCH /api/incidents/{id}/status`` and
therefore enforce the API's lifecycle state machine:

    OPEN → IN_PROGRESS | DISCARDED
    IN_PROGRESS → RESOLVED | DISCARDED
    RESOLVED → ∅
    DISCARDED → ∅
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError
from mcps.nexova_mcp.request_context import incoming_bearer_token
from services.api.models import (
    IncidentBranch,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentStatus,
)

# ── Timeout (seconds) ────────────────────────────────────────────────────
INCIDENT_TOOL_TIMEOUT_SECONDS = 5
TIMEOUT_MESSAGE = "No pude completar la operación sobre el ticket ahora mismo."


class ToolValidationError(ValueError):
    """Invalid arguments or domain values supplied to an MCP tool."""


def _api_access_token() -> str:
    """Return the authenticated caller token for the Incidents Manager API."""
    token = incoming_bearer_token.get()
    if not token:
        raise RuntimeError("La solicitud no contiene un token de usuario autenticado.")
    return token


# ---------------------------------------------------------------------------
def _incidents_api_url() -> str:
    """Return the configured API base URL for the Incidents Manager."""
    return os.environ.get("INCIDENTS_API_URL", "http://localhost:8000").rstrip("/")


def _incidents_endpoint(path: str = "") -> str:
    base_url = _incidents_api_url()
    if base_url.endswith("/api/incidents"):
        return f"{base_url}{path}"
    return f"{base_url}/api/incidents{path}"


def _api_request(method: str, path: str = "", **kwargs: Any) -> httpx.Response:
    """Call the authenticated Incidents Manager API with the MCP caller's token."""
    token = _api_access_token()
    try:
        return httpx.request(
            method,
            _incidents_endpoint(path),
            headers={"Authorization": f"Bearer {token}"},
            timeout=INCIDENT_TOOL_TIMEOUT_SECONDS,
            **kwargs,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(TIMEOUT_MESSAGE) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("No se pudo conectar con el Incidents Manager.") from exc


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

def _validate_positive_id(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ToolValidationError(f"'{field}' debe ser un entero mayor que cero.")


def lookup_incident(incident_id: int) -> dict[str, Any]:
    """Fetch an incident by ID from the Incidents Manager API."""
    _validate_positive_id(incident_id, "incident_id")
    response = _api_request("GET", f"/{incident_id}")
    if response.status_code == 404:
        return {"outcome": "not_found", "message": "No se encontro la incidencia solicitada."}
    if response.status_code in (401, 403):
        raise RuntimeError("El usuario no esta autorizado para consultar incidencias.")
    if response.status_code >= 400:
        raise RuntimeError(f"El Incidents Manager rechazo la consulta (HTTP {response.status_code}).")
    try:
        record = response.json()
    except ValueError as exc:
        raise RuntimeError("El Incidents Manager devolvio una respuesta no valida.") from exc
    return {"outcome": "found", "incident": _serialize(record)}

def list_incidents_tool(
    status: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
) -> list[dict[str, Any]]:
    """List incidents from the Incidents Manager API with optional filters."""
    params = {key: value for key, value in {
        "status": status, "category": category, "origin": origin, "branch": branch
    }.items() if value is not None}
    response = _api_request("GET", "", params=params)
    if response.status_code in (401, 403):
        raise RuntimeError("El usuario no esta autorizado para consultar incidencias.")
    if response.status_code >= 400:
        raise RuntimeError(f"El Incidents Manager rechazo la consulta (HTTP {response.status_code}).")
    try:
        documents = response.json()
    except ValueError as exc:
        raise RuntimeError("El Incidents Manager devolvio una respuesta no valida.") from exc
    if not isinstance(documents, list):
        raise RuntimeError("El Incidents Manager devolvio una respuesta no valida.")
    return [_serialize(document) for document in documents]

def create_incident_tool(
    title: str,
    description: str,
    category: str,
    status: str,
    origin: str,
    branch: str,
) -> dict[str, Any]:
    """Create an incident through the authenticated Incidents Manager API."""
    try:
        payload = IncidentCreate(
            title=title, description=description,
            category=IncidentCategory(category), status=IncidentStatus(status),
            origin=IncidentOrigin(origin), branch=IncidentBranch(branch),
        )
    except (ValidationError, ValueError) as exc:
        raise ToolValidationError(str(exc)) from exc
    response = _api_request("POST", "", json=payload.model_dump(mode="json"))
    if response.status_code in (400, 422):
        try:
            detail = response.json().get("detail", "Los datos de la incidencia no son validos.")
        except ValueError:
            detail = "Los datos de la incidencia no son validos."
        raise ToolValidationError(str(detail))
    if response.status_code in (401, 403):
        raise RuntimeError("El usuario no esta autorizado para crear incidencias.")
    if response.status_code >= 400:
        raise RuntimeError(f"El Incidents Manager rechazo la creacion (HTTP {response.status_code}).")
    try:
        return _serialize(response.json())
    except ValueError as exc:
        raise RuntimeError("El Incidents Manager devolvio una respuesta no valida.") from exc

def update_incident_status_tool(
    incident_id: int,
    new_status: str,
) -> dict[str, Any]:
    """Transition incident status using PATCH /api/incidents/{id}/status."""
    _validate_positive_id(incident_id, "incident_id")
    try:
        target = IncidentStatus(new_status)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in IncidentStatus)
        raise ToolValidationError(f"'new_status' debe ser uno de: {allowed}.") from exc
    response = _api_request("PATCH", f"/{incident_id}/status", json={"status": target.value})
    if response.status_code == 404:
        return {"outcome": "not_found", "message": "No se encontro la incidencia solicitada."}
    if response.status_code == 400:
        try:
            detail = response.json().get("detail", {})
        except ValueError:
            detail = {}
        message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
        return {"outcome": "error", "error": "invalid_transition", "message": message}
    if response.status_code in (401, 403):
        raise RuntimeError("El usuario no esta autorizado para actualizar incidencias.")
    if response.status_code >= 400:
        raise RuntimeError(f"El Incidents Manager rechazo la actualizacion (HTTP {response.status_code}).")
    try:
        return _serialize(response.json())
    except ValueError as exc:
        raise RuntimeError("El Incidents Manager devolvio una respuesta no valida.") from exc
