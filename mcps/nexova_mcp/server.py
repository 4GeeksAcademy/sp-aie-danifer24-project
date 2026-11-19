"""Nexova MCP Server — entry point.

Usage (development — SSE transport, compatible with MCP Playground):
    python -m mcps.nexova_mcp.server

The server is protected by OAuth 2.1 bearer‑token validation (own middleware).
Clients must present a valid JWT (same issuer as the Nexova FastAPI backend)
in the `Authorization: Bearer <token>` header.

Códigos de error (autenticación/autorización):
────────────────────────────────────────────
HTTP 401 → unauthorized / token_expired / invalid_token
Los fallos de autenticación se devuelven como HTTP 401. Los fallos de autorización,
validación, escritura de inventario y ejecución se devuelven como resultados MCP
estructurados con códigos ``insufficient_scope``, ``validation_error``,
``read_only_server`` o ``internal_error`` (el protocolo MCP transporta la respuesta
de la tool en una respuesta JSON-RPC). Ver ``mcps/nexova_mcp/auth.py``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

# ── Load .env before any service import reads env vars. ─────────────────
from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parents[2]
_env_file = _repo_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# ── Logging configuration (trazabilidad) ──────────────────────────────────
LOG_LEVEL = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
logger = logging.getLogger("nexova_mcp.server")

# ── fastmcp 4.x (wrapper around mcp 2.x MCPServer) ──────────────────────
from fastmcp import FastMCP

from mcps.nexova_mcp.auth import (
    PROTECTED_RESOURCE_METADATA,
    check_tool_authorization,
    introspect_token,
)
from mcps.nexova_mcp.request_context import incoming_bearer_token
from mcps.nexova_mcp.tools.incidents import (
    lookup_incident,
    list_incidents_tool,
    create_incident_tool,
    update_incident_status_tool,
    ToolValidationError,
)
from mcps.nexova_mcp.tools.inventory import (
    lookup_product,
    list_products as _list_inventory_products,
)
from mcps.nexova_mcp.tools.inventory_write_policy import reject_inventory_write

# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------
server = FastMCP(
    name="nexova-mcp",
    instructions=(
        "Nexova MCP Server — tools for managing support tickets "
        "(incidents) and querying product inventory. "
        "Authentication: OAuth 2.1 bearer token (JWT). "
        "See .well-known/oauth-authorization-server for metadata."
    ),
)



# ==========================================================================
# Wrapper de trazabilidad: registra cada invocación en logs
# ==========================================================================
import functools
import contextvars

# Almacén del payload del token usando contextvars (seguro para asyncio).
# El middleware lo establece antes de cada request HTTP, y las tools lo leen.
_token_payload_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar("token_payload", default=None)


class ToolAuthError(Exception):
    """Error de autorización lanzado por el wrapper de trazabilidad."""
    def __init__(self, message: str, error_code: str = "insufficient_scope"):
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def _with_tracing(func, public_name: str):
    """Wrap a tool with public-name authorization, tracing, and error mapping."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = public_name
        token_payload = _token_payload_var.get()

        # 1. Verificar autorización (scope enforcement)
        authorized, reason = check_tool_authorization(tool_name, token_payload)
        if not authorized:
            client_id = token_payload.get("sub", "anonymous") if token_payload else "anonymous"
            logger.warning(
                "Tool authorization DENIED: tool=%s client=%s reason=%s",
                tool_name,
                client_id,
                reason,
            )
            logger.info(
                "Tool completed: tool=%s client=%s outcome=error error=insufficient_scope",
                tool_name,
                client_id,
            )
            return {
                "outcome": "error",
                "error": "insufficient_scope",
                "message": reason,
            }

        # 2. Ejecutar la tool
        client_id = token_payload.get("sub", "unknown") if token_payload else "unknown"
        logger.info(
            "Tool invoked: tool=%s client=%s",
            tool_name,
            client_id,
        )
        try:
            result = func(*args, **kwargs)
        except (ToolValidationError, ValidationError, ValueError) as exc:
            result = {
                "outcome": "error",
                "error": "validation_error",
                "message": str(exc),
            }
        except Exception as exc:
            logger.error(
                "Tool FAILED: tool=%s client=%s error=%s",
                tool_name,
                client_id,
                str(exc),
                exc_info=True,
            )
            result = {
                "outcome": "error",
                "error": "internal_error",
                "message": "Ocurrió un error inesperado al procesar la solicitud.",
            }

        # Every invocation gets a completion log, including denials/errors.
        if isinstance(result, dict):
            outcome = result.get("outcome", result.get("error", "success"))
            result_code = result.get("error", "")
        elif isinstance(result, list):
            outcome = f"list({len(result)} items)"
            result_code = ""
        else:
            outcome = "success"
            result_code = ""
        logger.info(
            "Tool completed: tool=%s client=%s outcome=%s error=%s",
            tool_name,
            client_id,
            outcome,
            result_code,
        )
        return result

    return wrapper


def _register_tool(tool_fn, name: str | None = None, description: str | None = None):
    """Registra una tool con el wrapper de trazabilidad."""
    public_name = name or tool_fn.__name__
    wrapped = _with_tracing(tool_fn, public_name)
    server.tool(name=public_name, description=description or tool_fn.__doc__ or "")(wrapped)


# ==========================================================================
# TOOLS — Incidents Manager
# ==========================================================================

def _get_incident_impl(incident_id: Annotated[int, Field(gt=0, description="ID numérico de la incidencia, mayor que cero.")]) -> dict:
    """Fetch one incident by ID from the Incidents Manager."""
    return lookup_incident(incident_id)


def _list_incidents_impl(
    status: Annotated[Literal["open", "in_progress", "resolved", "discarded"] | None, Field(description="Filtra por estado actual.")] = None,
    category: Annotated[Literal["technical_failure", "process_error", "client_complaint", "candidate_issue", "staff_issue", "sla_breach", "data_quality", "other"] | None, Field(description="Filtra por categor?a.")] = None,
    origin: Annotated[Literal["customer", "branch", "internal"] | None, Field(description="Filtra por origen.")] = None,
    branch: Annotated[Literal["central", "valencia_operations", "miami_office", "remote"] | None, Field(description="Filtra por sede.")] = None,
) -> list[dict]:
    """List incidents from the Incidents Manager with optional filters."""
    return list_incidents_tool(
        status=status, category=category, origin=origin, branch=branch
    )


def _create_incident_impl(
    title: Annotated[str, Field(min_length=1, description="Título breve y no vacío.")],
    description: Annotated[str, Field(min_length=1, description="Descripción detallada no vacía.")],
    category: Annotated[Literal["technical_failure", "process_error", "client_complaint", "candidate_issue", "staff_issue", "sla_breach", "data_quality", "other"], Field(description="Categor?a de la incidencia.")],
    status: Annotated[Literal["open", "in_progress", "resolved", "discarded"], Field(description="Estado inicial.")],
    origin: Annotated[Literal["customer", "branch", "internal"], Field(description="Origen de la incidencia.")],
    branch: Annotated[Literal["central", "valencia_operations", "miami_office", "remote"], Field(description="Sede relacionada.")],
) -> dict:
    """Create a new incident in the Incidents Manager."""
    return create_incident_tool(
        title=title, description=description, category=category,
        status=status, origin=origin, branch=branch,
    )


def _update_incident_status_impl(
    incident_id: Annotated[int, Field(gt=0, description="ID numérico de la incidencia, mayor que cero.")],
    new_status: Annotated[Literal["open", "in_progress", "resolved", "discarded"], Field(description="Nuevo estado solicitado; sujeto a transiciones permitidas.")],
) -> dict:
    """Update an incident's status via the lifecycle endpoint."""
    return update_incident_status_tool(
        incident_id=incident_id, new_status=new_status
    )




# ==========================================================================
# TOOLS -- Inventory (read-only, write rejected by enforcement)
# ==========================================================================

def _get_product_impl(
    product_id: Annotated[int | None, Field(gt=0, description="ID num?rico del producto.")] = None,
    sku: Annotated[str | None, Field(min_length=1, description="SKU exacto o parcial.")] = None,
    name: Annotated[str | None, Field(min_length=1, description="Nombre exacto o parcial.")] = None,
) -> dict:
    """Fetch one product from the inventory."""
    return lookup_product(product_id=product_id, sku=sku, name=name)


def _list_products_impl(
    category: Annotated[str | None, Field(description="Categor?a del producto.")] = None,
    office: Annotated[str | None, Field(description="Oficina/ubicaci?n del producto.")] = None,
) -> list[dict]:
    """List inventory products."""
    return _list_inventory_products(category=category, office=office)


def _reject_inventory_write_impl(
    operation: Annotated[
        Literal["create", "update", "delete"],
        Field(description="Tipo de escritura intentada sobre el inventario."),
    ],
    product_id: Annotated[int | None, Field(gt=0, description="ID del producto existente, para update o delete.")] = None,
    name: Annotated[str | None, Field(min_length=1, description="Nombre del producto, para create o update.")] = None,
    sku: Annotated[str | None, Field(min_length=1, description="SKU del producto, para create o update.")] = None,
    category: Annotated[str | None, Field(description="Categoría del producto, para create.")] = None,
    office: Annotated[str | None, Field(description="Oficina/ubicación del producto, para create.")] = None,
) -> dict:
    """Explicitly reject inventory create, update, or delete attempts.

    This policy tool never performs or forwards a write operation.
    """
    return reject_inventory_write(
        operation=operation,
        product_id=product_id,
        name=name,
        sku=sku,
        category=category,
        office=office,
    )


# ── Registrar todas las tools con trazabilidad ──────────────────────────

_register_tool(
    _get_incident_impl,
    name="get_incident",
    description=(
        "Retrieve a single support ticket / incident by its numeric ID. "
        "Returns status, category, origin, branch, timestamps and full details. "
        "Use this when the user asks about a specific ticket number."
    ),
)

_register_tool(
    _list_incidents_impl,
    name="list_incidents",
    description=(
        "List support tickets / incidents with optional status, category, "
        "origin and branch filters.  Use this when the user asks for an "
        "overview or when they do not provide a specific ticket ID.  "
        "Returns an array of matching incident records."
    ),
)

_register_tool(
    _create_incident_impl,
    name="create_incident",
    description=(
        "Create a new support ticket / incident in the Incidents Manager. "
        "Requires title, description, category, status, origin and branch. "
        "All fields must match the Incidents Manager domain vocabulary."
    ),
)

_register_tool(
    _update_incident_status_impl,
    name="update_incident_status",
    description=(
        "Transition an incident to a new status. "
        "Uses the lifecycle endpoint (PATCH /api/incidents/{id}/status). "
        "Valid transitions: open -> in_progress | discarded, "
        "in_progress -> resolved | discarded.  "
        "Resolved / discarded tickets cannot transition further."
    ),
)

_register_tool(
    _get_product_impl,
    name="get_product",
    description=(
        "Retrieve a product and its current stock level by database ID, "
        "SKU or name.  Use this when the user asks about a specific "
        "product's availability or stock.  "
        "READ-ONLY -- any attempt to modify inventory data is explicitly denied."
    ),
)

_register_tool(
    _list_products_impl,
    name="list_products",
    description=(
        "List all products with current stock levels, optionally filtered "
        "by category or office. This is a read-only inventory catalogue."
    ),
)

_register_tool(
    _reject_inventory_write_impl,
    name="reject_inventory_write",
    description=(
        "Explicitly reject an attempted inventory mutation. Call this when "
        "asked to create, update, or delete a product. Requires operation "
        "(create, update, or delete); accepts optional product details for "
        "auditing only. This tool never changes data and returns the "
        "read_only_server error."
    ),
)
# ==========================================================================
# Middleware ASGI para inyectar el token payload en cada request
# ==========================================================================
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send


class TokenContextMiddleware:
    """Middleware OAuth propio (ASGI puro, sin mcpauth).

    1. Extrae el header ``Authorization: Bearer <token>``.
    2. Valida el JWT via ``introspect_token()``.
    3. Inyecta el payload en las tools via ``_set_current_token_payload()``.
    4. Rechaza con 401 si no hay token o es inválido.

    Se aplica manualmente envolviendo la app ASGI final en ``main()``.
    """

    PUBLIC_PATHS = {
        "/.well-known/oauth-authorization-server",
        "/health",
        "/sse",
    }

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path in self.PUBLIC_PATHS:
            _token_payload_var.set(None)
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw = headers.get(b"authorization", b"").decode().strip().strip('"').strip("'")

        # Enforce the OAuth bearer scheme; never accept a raw token or another scheme.
        scheme, separator, credential = raw.partition(" ")
        token = credential.strip() if separator and scheme.casefold() == "bearer" else None

        if not token:
            resp = JSONResponse(
                {"error": "unauthorized",
                 "message": "Se requiere un token de acceso. Usa el header 'Authorization: Bearer <token>'."},
                status_code=401,
            )
            await resp(scope, receive, send)
            return

        payload = introspect_token(token)
        if not payload.get("active"):
            error = payload.get("error", "invalid_token")
            message = payload.get("message", "El token de acceso no es válido o ha expirado.")
            resp = JSONResponse(
                {"error": error, "message": message},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer error="{error}"'},
            )
            await resp(scope, receive, send)
            return

        payload_token = _token_payload_var.set(payload)
        bearer_token = incoming_bearer_token.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            incoming_bearer_token.reset(bearer_token)
            _token_payload_var.reset(payload_token)


# ==========================================================================
# Entry point
# ==========================================================================
@server.custom_route(
    "/.well-known/oauth-authorization-server",
    methods=["GET"],
    include_in_schema=False,
)
async def _metadata_endpoint(request):
    """Publish OAuth resource metadata without registering a FastMCP subserver."""
    from starlette.responses import JSONResponse

    return JSONResponse(PROTECTED_RESOURCE_METADATA)


def _apply_middleware(app: ASGIApp) -> ASGIApp:
    """Envuelve la app ASGI con TokenContextMiddleware manualmente."""
    return TokenContextMiddleware(app)


async def main() -> None:
    """Run the MCP server with SSE transport (MCP estándar).

    Compatible with MCP Playground, MCP Inspector and any MCP client.
    """
    HOST = os.environ.get("MCP_HOST", "0.0.0.0")
    PORT = int(os.environ.get("MCP_PORT", "8010"))

    logger.info("OAuth metadata endpoint registered at /.well-known/oauth-authorization-server")

    # Construir la app ASGI (sin middleware Starlette) y aplicarlo manualmente
    app = server.http_app(transport="sse")
    app = _apply_middleware(app)
    logger.info("OAuth bearer-token middleware (TokenContextMiddleware) applied.")

    # Arrancar Uvicorn directamente con la app envuelta
    import uvicorn
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower() if LOG_LEVEL else "info",
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
