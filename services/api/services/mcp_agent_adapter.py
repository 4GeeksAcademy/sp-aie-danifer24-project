"""
MCP Agent Adapter — replaces direct tool calls in the LangGraph agent with
calls routed through the Nexova MCP Server.

This module provides drop-in replacements for:
  - ``services.api.services.incident_tool.lookup_incidents``
  - ``services.api.services.inventory_tool.lookup_inventory``

These functions have the same input/output contracts as the originals,
but delegate to the MCP Server instead of TinyDB / PostgreSQL directly.

Usage:
    from services.api.services.mcp_agent_adapter import (
        lookup_incidents_mcp,
        lookup_inventory_mcp,
    )

    # Pass to the graph builder:
    graph = build_knowledge_graph(
        incident_fn=lookup_incidents_mcp,
        inventory_fn=lookup_inventory_mcp,
    )
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure .env is loaded
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from services.api.services.incident_tool import (
    IncidentLookupInput,
    IncidentLookupOutput,
    IncidentRecord,
    IncidentToolOutcome,
)
from services.api.services.inventory_tool import (
    InventoryLookupInput,
    InventoryLookupOutput,
    InventoryToolOutcome,
)

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8010/mcp")
MCP_CLIENT_TIMEOUT = float(os.environ.get("MCP_CLIENT_TIMEOUT", "10"))


# ==========================================================================
#  MCP Client (lazy singleton, async init)
# ==========================================================================

class _MCPClientProxy:
    """Lazy proxy to NexovaMCPClient that initializes on first use."""

    def __init__(self):
        self._client = None
        self._connected = False

    def _ensure(self):
        if not self._connected:
            from mcps.nexova_mcp.mcp_client import NexovaMCPClient
            self._client = NexovaMCPClient(
                server_url=MCP_SERVER_URL,
                timeout=MCP_CLIENT_TIMEOUT,
            )
            self._connected = True
        return self._client

    def get_incident(self, incident_id: int) -> dict:
        return self._ensure().get_incident(incident_id)

    def list_incidents(self, **filters) -> dict:
        return self._ensure().list_incidents(**filters)

    def get_product(self, **kwargs) -> dict:
        return self._ensure().get_product(**kwargs)

    def list_products(self, **kwargs) -> dict:
        return self._ensure().list_products(**kwargs)


_client_proxy = _MCPClientProxy()


# ==========================================================================
#  Incident adapter — replaces ``incident_tool.lookup_incidents``
# ==========================================================================

from services.api.models import (
    IncidentBranch,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
)


def _parse_incident_record(raw: dict) -> IncidentRecord:
    """Parse a raw dict from the MCP tool into an IncidentRecord."""
    return IncidentRecord(
        id=int(raw.get("id", 0)),
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        status=IncidentStatus(raw.get("status", "open")),
        category=IncidentCategory(raw.get("category", "other")),
        origin=IncidentOrigin(raw.get("origin", "internal")),
        branch=IncidentBranch(raw.get("branch", "central")),
        created_at=datetime.fromisoformat(raw["created_at"]) if "created_at" in raw else datetime.now(),
        updated_at=datetime.fromisoformat(raw["updated_at"]) if "updated_at" in raw else datetime.now(),
    )


def lookup_incidents_mcp(request: IncidentLookupInput) -> IncidentLookupOutput:
    """Replace ``incident_tool.lookup_incidents`` via MCP Server.

    Input/Output contracts are identical to the original.
    """
    logger.info(
        "mcp_adapter.lookup_incidents called: ticket_id=%s filters=%s",
        request.ticket_id,
        {
            "status": request.status,
            "category": request.category,
            "origin": request.origin,
            "branch": request.branch,
        },
    )
    try:
        if request.ticket_id is not None:
            result = _client_proxy.get_incident(request.ticket_id)
            if result.get("outcome") == "found":
                incident = result.get("incident", {})
                records = [_parse_incident_record(incident)]
                return IncidentLookupOutput(
                    outcome=IncidentToolOutcome.FOUND,
                    incidents=records,
                )
            elif result.get("outcome") == "not_found":
                return IncidentLookupOutput(
                    outcome=IncidentToolOutcome.NOT_FOUND,
                    message="No se encontró la incidencia solicitada.",
                )
            else:
                return IncidentLookupOutput(
                    outcome=IncidentToolOutcome.ERROR,
                    message="No pude confirmar el estado de ese ticket ahora mismo.",
                )
        else:
            result = _client_proxy.list_incidents(
                status=request.status.value if request.status else None,
                category=request.category.value if request.category else None,
                origin=request.origin.value if request.origin else None,
                branch=request.branch.value if request.branch else None,
            )
            if isinstance(result, dict) and result.get("outcome") == "found":
                records = [_parse_incident_record(r) for r in result.get("incidents", [])]
                if not records:
                    return IncidentLookupOutput(
                        outcome=IncidentToolOutcome.NOT_FOUND,
                        message="No se encontraron incidencias con esos filtros.",
                    )
                return IncidentLookupOutput(
                    outcome=IncidentToolOutcome.FOUND,
                    incidents=records,
                )
            elif isinstance(result, list):
                records = [_parse_incident_record(r) for r in result]
                if not records:
                    return IncidentLookupOutput(
                        outcome=IncidentToolOutcome.NOT_FOUND,
                        message="No se encontraron incidencias.",
                    )
                return IncidentLookupOutput(
                    outcome=IncidentToolOutcome.FOUND,
                    incidents=records,
                )
            return IncidentLookupOutput(
                outcome=IncidentToolOutcome.ERROR,
                message="No pude confirmar los tickets ahora mismo.",
            )
    except Exception as exc:
        logger.error("MCP incident lookup failed: %s", exc, exc_info=True)
        return IncidentLookupOutput(
            outcome=IncidentToolOutcome.ERROR,
            message=(
                "No pude confirmar el estado de ese ticket ahora mismo. "
                "El servidor MCP de incidencias no está disponible."
            ),
        )


# ==========================================================================
#  Inventory adapter — replaces ``inventory_tool.lookup_inventory``
# ==========================================================================

from services.api.schemas import AssetResponse


def _parse_product(raw: dict) -> AssetResponse:
    """Parse a raw dict from the MCP tool into an AssetResponse."""
    return AssetResponse(
        id=int(raw.get("id", 0)),
        name=raw.get("name", ""),
        sku=raw.get("sku", ""),
        category=raw.get("category", ""),
        office=raw.get("office", ""),
        current_stock=int(raw.get("current_stock", 0)),
        product_category=raw.get("product_category", ""),
        programme_id=raw.get("programme_id"),
    )


def lookup_inventory_mcp(request: InventoryLookupInput) -> InventoryLookupOutput:
    """Replace ``inventory_tool.lookup_inventory`` via MCP Server.

    Input/Output contracts are identical to the original.
    """
    logger.info(
        "mcp_adapter.lookup_inventory called: product_id=%s sku=%s name=%s",
        request.product_id,
        request.sku,
        request.name,
    )
    try:
        result = _client_proxy.get_product(
            product_id=request.product_id,
            sku=request.sku,
            name=request.name,
        )
        if result.get("outcome") == "found":
            product = result.get("product", {})
            records = [_parse_product(product)]
            return InventoryLookupOutput(
                outcome=InventoryToolOutcome.FOUND,
                products=records,
            )
        elif result.get("outcome") == "not_found":
            return InventoryLookupOutput(
                outcome=InventoryToolOutcome.NOT_FOUND,
                message="No encontré un producto que coincida con la consulta.",
            )
        else:
            return InventoryLookupOutput(
                outcome=InventoryToolOutcome.ERROR,
                message="No pude confirmar el stock del producto ahora mismo.",
            )
    except Exception as exc:
        logger.error("MCP inventory lookup failed: %s", exc, exc_info=True)
        return InventoryLookupOutput(
            outcome=InventoryToolOutcome.ERROR,
            message=(
                "No pudo confirmar el stock del producto ahora mismo. "
                "El servidor MCP de inventario no está disponible."
            ),
        )