"""
MCP Auth — OAuth 2.1 / OIDC bearer‑token validation for the Nexova MCP Server.

We use `mcpauth` to mount:
  - `.well-known/oauth-authorization-server` (Protected Resource Metadata)
  - Token introspection endpoint
  - Bearer‑token enforcement on every tool call

Tokens are JWT‑encoded with the same `JWT_SECRET_KEY` and `JWT_ALGORITHM` that
the Nexova FastAPI backend uses, so any client that holds a valid access token
for the API can reuse it with the MCP server.

────────────────────────────────────────────────────────────────────────
Códigos de error / salida esperados (autenticación y autorización):
────────────────────────────────────────────────────────────────────────

HTTP 401 — Unauthenticated
────────────────────
  { "error": "unauthorized", "message": "Se requiere un token de acceso." }
  → El cliente no presentó token o el token no es un bearer JWT válido.
  → Causa: cabecera Authorization ausente, malformada o con esquema
    distinto a "Bearer".

HTTP 401 — Token expired
────────────────────
  { "error": "token_expired",
    "message": "El token de acceso ha expirado. Solicita uno nuevo." }
  → El JWT está bien formado pero su claim ``exp`` es anterior a la
    hora actual del servidor.
  → Causa: el cliente usa un token cuyo tiempo de vida venció.

HTTP 401 — Token invalid
────────────────────
  { "error": "invalid_token",
    "message": "El token de acceso no es válido o está mal formado." }
  → El JWT no pudo decodificarse (firma inválida, payload corrupto,
    claims requeridos ``sub``/``exp`` ausentes).
  → Causa: token manipulado, emitido por otro issuer o malformado.

HTTP 403 — Forbidden (scope insuficiente)
────────────────────
  { "error": "insufficient_scope",
    "message": "El token no tiene los permisos necesarios para esta
    herramienta. Se requiere al menos uno de: <scopes>." }
  → El token es activo y válido pero su claim ``scope`` no contiene
    ningún scope del conjunto requerido por la tool invocada.
  → Causa: el cliente autenticado no está autorizado para la tool.

Error de tool — Escritura de inventario rechazada
────────────────────
  { "outcome": "error", "error": "read_only_server",
    "message": "El inventario es de solo lectura en este servidor MCP. ..." }
  → Se invocó reject_inventory_write para una operación de create, update
    o delete. La solicitud se registra pero nunca accede a la base de datos.

HTTP 422 — Validation error
────────────────────
  { "error": "validation_error",
    "message": "<descripción del problema concreto>" }
  → Los parámetros de la tool no pasaron la validación de tipos o
    dominio (ej. status inválido, categoría desconocida, ID negativo).
  → Causa: el cliente envió datos que no cumplen el esquema de la tool.

HTTP 500 — Internal error
────────────────────
  { "error": "internal_error",
    "message": "Ocurrió un error inesperado al procesar la solicitud." }
  → Error no clasificado durante la ejecución de la tool.
  → Causa: fallo de infraestructura (BD caída, excepción no capturada).

────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jose import ExpiredSignatureError, JWTError, jwt

logger = logging.getLogger("nexova_mcp.auth")

# ---------------------------------------------------------------------------
# Load env from project root
# ---------------------------------------------------------------------------
# Walk up from mcps/nexova-mcp/auth.py to find .env at the repo root.
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY must be configured in .env or the environment "
        "for MCP OAuth bearer validation."
    )

JWT_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# Well‑known OAuth Protected Resource Metadata
# (published at /.well-known/oauth-authorization-server)
# ---------------------------------------------------------------------------
PROTECTED_RESOURCE_METADATA: dict[str, Any] = {
    "issuer": "http://localhost:8010",
    "token_endpoint": None,  # This resource server does not mint tokens.
    "token_introspection_endpoint": "/introspect",
    "scopes_supported": ["incidents:read", "incidents:write", "inventory:read"],
    "response_types_supported": ["token"],
    "token_endpoint_auth_methods_supported": [],
    "bearer": {
        "token_type": "bearer",
        "token_encoding": "Base64Url-encoded-JWT",
    },
}

# Map of MCP tool names → required scope(s).
# Principio de mínimo privilegio: cada tool solo tiene los scopes
# estrictamente necesarios para su función.
TOOL_SCOPE_MAP: dict[str, set[str]] = {
    # ── Incident tools (lectura) ──────────────────────────────────────
    "get_incident": {"incidents:read"},
    "list_incidents": {"incidents:read"},
    # ── Incident tools (escritura — requieren incidents:write) ────────
    "create_incident": {"incidents:write"},
    "update_incident_status": {"incidents:write"},
    # ── Inventory tools (solo lectura, incluido rechazo explícito) ──────
    "get_product": {"inventory:read"},
    "list_products": {"inventory:read"},
    "reject_inventory_write": {"inventory:read"},
}


# ---------------------------------------------------------------------------
# Token introspection (called by mcpauth's middleware)
# ---------------------------------------------------------------------------
def introspect_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT bearer token.

    Returns an introspection response following RFC 7662.  A token is
    considered *active* when the signature is valid and the token has not
    expired.
    """
    result: dict[str, Any] = {
        "active": False,
        "token_type": "bearer",
    }
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except ExpiredSignatureError:
        logger.warning("Token introspection failed: expired token")
        result["error"] = "token_expired"
        result["message"] = "El token de acceso ha expirado. Solicita uno nuevo."
        return result
    except JWTError:
        logger.warning("Token introspection failed: JWT decode error (invalid signature or malformed)")
        result["error"] = "invalid_token"
        result["message"] = "El token de acceso no es válido o está mal formado."
        return result

    # Reject non‑access tokens (e.g. password‑reset tokens).
    if payload.get("purpose", "access") != "access":
        logger.warning(
            "Token rejected: purpose=%s (expected 'access')",
            payload.get("purpose"),
        )
        return result

    # Reject expired tokens.
    exp = payload.get("exp")
    now = datetime.now(tz=timezone.utc)
    if exp is not None and datetime.fromtimestamp(exp, tz=timezone.utc) < now:
        logger.warning("Token rejected: expired (exp=%d, now=%d)", exp, int(now.timestamp()))
        return result

    # Build introspection response ── map "sub" → "user_id".
    result["active"] = True
    result["sub"] = payload.get("sub")
    result["user_id"] = payload.get("sub")
    result["exp"] = payload.get("exp")
    result["iat"] = payload.get("iat")
    result["scope"] = payload.get("scope", "")
    logger.info(
        "Token introspection succeeded: sub=%s scopes=%s",
        payload.get("sub"),
        payload.get("scope", ""),
    )
    return result


def get_required_scopes(tool_name: str) -> list[str]:
    """Return the sorted list of scopes needed to invoke *tool_name*."""
    return sorted(TOOL_SCOPE_MAP.get(tool_name, set()))


def check_tool_authorization(
    tool_name: str, token_payload: dict[str, Any] | None
) -> tuple[bool, str | None]:
    """Verify that *token_payload* (from introspection) grants access to *tool_name*.

    This is a second gate *after* mcpauth's bearer validation — the server
    can reject a tool invocation even if the token is valid, based on the
    tool's required scopes.

    Parameters
    ----------
    tool_name : str
        Name of the tool being invoked.
    token_payload : dict | None
        Introspection response from ``introspect_token()``.

    Returns
    -------
    (bool, str | None)
        ``(True, None)`` if authorized.
        ``(False, error_message)`` if denied, where *error_message* is a
        human-readable string explaining why, suitable for returning to
        the client via the tool's outcome dict.
    """
    if not token_payload or not token_payload.get("active"):
        return False, (
            "Autenticación requerida: el token de acceso no está activo "
            "o la solicitud no incluye un bearer token válido."
        )

    # Fail closed: every exposed tool must declare its required scope.
    # Read-only denial tools still require inventory:read so they cannot be
    # used as an unauthenticated oracle or to enumerate server behavior.
    required = TOOL_SCOPE_MAP.get(tool_name)
    if required is None:
        return False, f"No hay una política de autorización configurada para '{tool_name}'."

    # Verificar scopes del token
    token_scopes = _parse_scopes(token_payload.get("scope", ""))
    if not token_scopes or not token_scopes.intersection(required):
        return False, (
            f"Permiso insuficiente para '{tool_name}'. "
            f"Se requiere al menos uno de: {', '.join(sorted(required))}. "
            f"Scopes del token: {', '.join(sorted(token_scopes)) or '(ninguno)'}."
        )

    return True, None


def _parse_scopes(scope_str: str) -> set[str]:
    """Parse a space-separated scope string into a set of scope names."""
    return set(scope_str.strip().split()) if scope_str else set()
