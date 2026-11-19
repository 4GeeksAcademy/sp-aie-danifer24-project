"""Explicit read-only policy for inventory mutations exposed through MCP."""

from __future__ import annotations

from typing import Any

WRITE_DENIED_MESSAGE = (
    "El inventario es de solo lectura en este servidor MCP. "
    "No se permiten operaciones de creación, actualización ni eliminación."
)


def reject_inventory_write(
    operation: str,
    product_id: int | None = None,
    name: str | None = None,
    sku: str | None = None,
    category: str | None = None,
    office: str | None = None,
) -> dict[str, Any]:
    """Reject any inventory write attempt without accessing or changing data."""
    return {
        "outcome": "error",
        "error": "read_only_server",
        "message": WRITE_DENIED_MESSAGE,
        "operation": operation,
    }
