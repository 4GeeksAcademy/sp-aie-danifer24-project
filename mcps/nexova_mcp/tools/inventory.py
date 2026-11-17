"""
Inventory MCP tools — **read‑only by design**.

Any attempt to create, update or delete a product is explicitly rejected at
the server level with a ``WriteDenied`` error.  This is not an omission of
write endpoints — it is an enforced policy that every mutation path returns
an error.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from services.api.database import engine
from services.api.models import Asset
from services.api.services.inventory import inventory_product_response
from services.api.schemas import AssetResponse

# ── Timeout (seconds) ────────────────────────────────────────────────────
INVENTORY_TOOL_TIMEOUT_SECONDS = 5
TIMEOUT_MESSAGE = "No pude consultar el inventario ahora mismo."

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def lookup_product(
    product_id: int | None = None,
    sku: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Retrieve a product and its current stock by database ID, SKU, or name.

    Parameters
    ----------
    product_id : int, optional
        Product database ID (> 0).
    sku : str, optional
        SKU to search (case‑insensitive partial match).
    name : str, optional
        Product name (case‑insensitive partial match).

    Returns
    -------
    dict
        Product record with fields: id, name, sku, category, office,
        current_stock, product_category, programme_id.
        If not found: {"outcome": "not_found", "message": "..."}.
    """
    if not any((product_id, sku, name)):
        return {
            "outcome": "error",
            "message": (
                "Proporciona un ID de producto, SKU o nombre. "
                "No se permiten consultas de stock sin filtro."
            ),
        }

    with Session(engine) as session:
        statement = select(Asset)
        if product_id is not None:
            statement = statement.where(Asset.id == product_id)
        if sku:
            statement = statement.where(Asset.sku.ilike(f"%{sku}%"))
        if name:
            statement = statement.where(Asset.name.ilike(f"%{name}%"))
        asset = session.exec(statement.order_by(Asset.id)).first()

    if asset is None:
        return {
            "outcome": "not_found",
            "message": "No encontré un producto que coincida con la consulta.",
        }

    with Session(engine) as session:
        response = inventory_product_response(session, asset)
    return {"outcome": "found", "product": response.model_dump(mode="json")}


def list_products(
    category: str | None = None,
    office: str | None = None,
) -> list[dict[str, Any]]:
    """List all products with current stock, optionally filtered.

    Parameters
    ----------
    category : str, optional
        Filter by asset category: hardware, peripherals, office_supplies,
        training_materials.
    office : str, optional
        Filter by office: Valencia, Miami.

    Returns
    -------
    list[dict]
        Array of product records.  Each record contains id, name, sku,
        category, office, current_stock, product_category, programme_id.
    """
    with Session(engine) as session:
        statement = select(Asset)
        if category:
            statement = statement.where(Asset.category == category)
        if office:
            statement = statement.where(Asset.office == office)
        assets = session.exec(statement.order_by(Asset.id)).all()
        return [
            inventory_product_response(session, asset).model_dump(mode="json")
            for asset in assets
        ]


# ── Explicit write denial (policy enforcement, not omission) ─────────────

WRITE_DENIED_MESSAGE = (
    "El servidor MCP de inventario es exclusivamente de consulta. "
    "Las operaciones de escritura no están permitidas por diseño."
)


def _reject_write() -> dict[str, Any]:
    """Explicitly reject any mutation attempt on inventory data."""
    return {
        "outcome": "denied",
        "message": WRITE_DENIED_MESSAGE,
    }