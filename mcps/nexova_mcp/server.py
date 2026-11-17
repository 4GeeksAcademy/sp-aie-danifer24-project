"""Nexova MCP Server — entry point.

Usage (development — Streamable HTTP):
    python -m mcps.nexova_mcp.server

The server is protected by OAuth 2.1 bearer‑token validation (mcpauth).
Clients must present a valid JWT (same issuer as the Nexova FastAPI backend)
in the `Authorization: Bearer <token>` header.

Códigos de error (autenticación/autorización):
────────────────────────────────────────────
HTTP 401 → unauthorized / token_expired / invalid_token
HTTP 403 → insufficient_scope
HTTP 405 → read_only_server
HTTP 422 → validation_error
HTTP 500 → internal_error
Ver ``mcps/nexova_mcp/auth.py`` para la documentación completa.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

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

# ── mcpauth: OAuth 2.1 / OIDC bearer-token validation ────────────────────
from mcpauth import MCPAuth
from mcpauth.config import AuthServerConfig

# ── fastmcp 4.x (wrapper around mcp 2.x MCPServer) ──────────────────────
from fastmcp import FastMCP

from mcps.nexova_mcp.auth import (
    PROTECTED_RESOURCE_METADATA,
    check_tool_authorization,
    introspect_token,
)
from mcps.nexova_mcp.tools.incidents import (
    lookup_incident,
    list_incidents_tool,
    create_incident_tool,
    update_incident_status_tool,
    delete_incident_tool,
)
from mcps.nexova_mcp.tools.inventory import (
    lookup_product,
    list_products as _list_inventory_products,
    _reject_write,
)

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

# ── OAuth configuration (used at startup in main()) ────────────────────
from mcpauth.config import (
    AuthorizationServerMetadata,
    AuthServerType,
)


def _build_bearer_middleware() -> type[BaseHTTPMiddleware] | None:
    """Build the mcpauth bearer-token middleware class.

    Returns None if mcpauth rejects the configuration (the server will
    start WITHOUT authentication in that case).
    """
    try:
        meta = AuthorizationServerMetadata(
            issuer=PROTECTED_RESOURCE_METADATA["issuer"],
            authorization_endpoint="http://localhost:8010/authorize",
            token_endpoint="http://localhost:8010/token",
            response_types_supported=["code"],
            grant_types_supported=["authorization_code"],
            code_challenge_methods_supported=["S256"],
        )
        cfg = AuthServerConfig(metadata=meta, type=AuthServerType.OAUTH)
        mcp_auth = MCPAuth(server=cfg)
        return mcp_auth.bearer_auth_middleware(
            mode_or_verify=introspect_token,
            show_error_details=True,
        )
    except Exception as exc:
        logger.warning("Could not build mcpauth config: %s", exc)
        return None


# Pre-build once at module level
_BEARER_MW = _build_bearer_middleware()


# ==========================================================================
# Wrapper de trazabilidad: registra cada invocación en logs
# ==========================================================================
import functools

# Almacén temporal del payload del token para la request actual.
# Lo establece el middleware antes de llegar a la tool.
_current_token_payload: dict | None = None


def _set_current_token_payload(payload: dict | None) -> None:
    """Establece el payload del token para la request actual (llamado desde middleware)."""
    global _current_token_payload
    _current_token_payload = payload


def _get_current_token_payload() -> dict | None:
    """Recupera el payload del token para la request actual."""
    return _current_token_payload


class ToolAuthError(Exception):
    """Error de autorización lanzado por el wrapper de trazabilidad."""
    def __init__(self, message: str, error_code: str = "insufficient_scope"):
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def _with_tracing(func):
    """Decorador que envuelve cada tool con:
    - Verificación de autorización (scope enforcement)
    - Log de invocación (qué tool, qué cliente, qué resultado)
    - Captura de errores con códigos de salida documentados
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        token_payload = _get_current_token_payload()

        # 1. Verificar autorización (scope enforcement)
        authorized, reason = check_tool_authorization(tool_name, token_payload)
        if not authorized:
            logger.warning(
                "Tool authorization DENIED: tool=%s client=%s reason=%s",
                tool_name,
                token_payload.get("sub", "anonymous") if token_payload else "anonymous",
                reason,
            )
            return {
                "outcome": "error",
                "error": "insufficient_scope",
                "message": reason,
            }

        # 2. Ejecutar la tool
        client_id = token_payload.get("sub", "unknown") if token_payload else "unknown"
        logger.info(
            "Tool invoked: tool=%s client=%s args=%s",
            tool_name,
            client_id,
            {k: v for k, v in kwargs.items() if k != "password"},
        )
        try:
            result = func(*args, **kwargs)
            # Determinar outcome para el log
            outcome = "unknown"
            if isinstance(result, dict):
                outcome = result.get("outcome", result.get("error", "success"))
            elif isinstance(result, list):
                outcome = f"list({len(result)} items)"
            logger.info(
                "Tool completed: tool=%s client=%s outcome=%s",
                tool_name,
                client_id,
                outcome,
            )
            return result
        except Exception as exc:
            logger.error(
                "Tool FAILED: tool=%s client=%s error=%s",
                tool_name,
                client_id,
                str(exc),
                exc_info=True,
            )
            return {
                "outcome": "error",
                "error": "internal_error",
                "message": "Ocurrió un error inesperado al procesar la solicitud.",
            }

    return wrapper


def _register_tool(tool_fn, name: str | None = None, description: str | None = None):
    """Registra una tool con el wrapper de trazabilidad."""
    wrapped = _with_tracing(tool_fn)
    server.tool(name=name or tool_fn.__name__, description=description or tool_fn.__doc__ or "")(wrapped)


# ==========================================================================
# TOOLS — Incidents Manager
# ==========================================================================

def _get_incident_impl(incident_id: int) -> dict:
    """Fetch one incident by ID from the Incidents Manager."""
    return lookup_incident(incident_id)


def _list_incidents_impl(
    status: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
) -> list[dict]:
    """List incidents from the Incidents Manager with optional filters."""
    return list_incidents_tool(
        status=status, category=category, origin=origin, branch=branch
    )


def _create_incident_impl(
    title: str,
    description: str,
    category: str,
    status: str,
    origin: str,
    branch: str,
) -> dict:
    """Create a new incident in the Incidents Manager."""
    return create_incident_tool(
        title=title, description=description, category=category,
        status=status, origin=origin, branch=branch,
    )


def _update_incident_status_impl(incident_id: int, new_status: str) -> dict:
    """Update an incident's status via the lifecycle endpoint."""
    return update_incident_status_tool(
        incident_id=incident_id, new_status=new_status
    )


def _delete_incident_impl(incident_id: int) -> dict:
    """Delete an incident."""
    return delete_incident_tool(incident_id=incident_id)


# ==========================================================================
# TOOLS -- Inventory (read-only, write rejected by enforcement)
# ==========================================================================

def _get_product_impl(
    product_id: int | None = None,
    sku: str | None = None,
    name: str | None = None,
) -> dict:
    """Fetch one product from the inventory."""
    return lookup_product(product_id=product_id, sku=sku, name=name)


def _list_products_impl(
    category: str | None = None,
    office: str | None = None,
) -> list[dict]:
    """List inventory products."""
    return _list_inventory_products(category=category, office=office)


def _create_product_impl(
    name: str = "",
    sku: str = "",
    category: str = "",
    office: str = "",
) -> dict:
    """Denied: inventory is read-only."""
    return _reject_write()


def _update_product_impl(
    product_id: int = 0,
    name: str = "",
    sku: str = "",
) -> dict:
    """Denied: inventory is read-only."""
    return _reject_write()


def _delete_product_impl(product_id: int = 0) -> dict:
    """Denied: inventory is read-only."""
    return _reject_write()


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
    _delete_incident_impl,
    name="delete_incident",
    description=(
        "Permanently delete an incident record.  Use sparingly -- "
        "prefer status transitions over deletion."
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
        "by category or office.  This is the inventory catalogue.  "
        "READ-ONLY -- write attempts are explicitly rejected."
    ),
)

_register_tool(
    _create_product_impl,
    name="create_product",
    description=(
        "READ-ONLY SERVER -- Inventory write operations are not allowed.  "
        "This tool exists solely to return an explicit denial message.  "
        "Use the FastAPI backend at /inventory/products for product creation."
    ),
)

_register_tool(
    _update_product_impl,
    name="update_product",
    description=(
        "READ-ONLY SERVER -- Inventory write operations are not allowed.  "
        "This tool exists solely to return an explicit denial message."
    ),
)

_register_tool(
    _delete_product_impl,
    name="delete_product",
    description=(
        "READ-ONLY SERVER -- Inventory write operations are not allowed.  "
        "This tool exists solely to return an explicit denial message."
    ),
)


# ==========================================================================
# Middleware ASGI para inyectar el token payload en cada request
# ==========================================================================
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TokenContextMiddleware(BaseHTTPMiddleware):
    """Middleware ASGI que extrae el payload del token de la request
    (inyectado por mcpauth) y lo pone a disposición de las tools
    via ``_set_current_token_payload()`` antes de cada invocación.
    """

    async def dispatch(self, request: Request, call_next):
        # El payload del token lo deja mcpauth en request.state.token_introspection
        payload = getattr(request.state, "token_introspection", None) if hasattr(request, "state") else None
        _set_current_token_payload(payload)
        response = await call_next(request)
        _set_current_token_payload(None)
        return response


# ==========================================================================
# Entry point
# ==========================================================================
async def main() -> None:
    """Run the MCP server with Streamable HTTP transport via uvicorn."""
    HOST = os.environ.get("MCP_HOST", "0.0.0.0")
    PORT = int(os.environ.get("MCP_PORT", "8010"))

    # Build middleware list
    mw_list: list = []

    # 1. mcpauth bearer-token middleware (autenticación)
    if _BEARER_MW is not None:
        try:
            mw_list.append(_BEARER_MW())
            logger.info("mcpauth bearer-token middleware added.")
        except Exception as exc:
            logger.warning(
                "Could not instantiate mcpauth middleware: %s. "
                "Proceeding WITHOUT authentication.",
                exc,
            )
    else:
        logger.warning("No mcpauth config -- server starting WITHOUT auth.")

    # 2. TokenContextMiddleware (inyecta token payload a las tools)
    mw_list.append(TokenContextMiddleware())

    # Build the ASGI app with middleware
    from starlette.responses import JSONResponse

    async def metadata_endpoint(request):
        return JSONResponse(PROTECTED_RESOURCE_METADATA)

    app = server.http_app(middleware=mw_list if mw_list else None)

    # Add metadata route to the Starlette app
    try:
        app.add_route(
            "/.well-known/oauth-authorization-server",
            metadata_endpoint,
            methods=["GET"],
        )
        logger.info("Metadata endpoint at /.well-known/oauth-authorization-server")
    except Exception as exc:
        logger.warning("Could not mount metadata endpoint: %s", exc)

    # Print banner
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    print(f"\nNexova MCP Server starting on http://{HOST}:{PORT}", flush=True)
    print(
        "   OAuth Protected Resource Metadata: "
        f"http://{HOST}:{PORT}/.well-known/oauth-authorization-server",
        flush=True,
    )
    print(f"   Tools ({len(tool_names)}): {', '.join(sorted(tool_names))}", flush=True)
    print()

    # Serve with uvicorn directly, passing the pre-built app
    import uvicorn

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
    server_uvicorn = uvicorn.Server(config)
    await server_uvicorn.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
