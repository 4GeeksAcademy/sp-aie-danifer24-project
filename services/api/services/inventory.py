"""Read-only inventory product queries shared by the API and support tool."""

from sqlmodel import Session, select
from sqlalchemy import func

from services.api.models import Asset, AssetEntry, AssetExit
from services.api.schemas import AssetResponse


def inventory_product_response(session: Session, asset: Asset) -> AssetResponse:
    """Build the same product/stock projection exposed by GET /inventory/products."""
    entries = session.exec(
        select(func.coalesce(func.sum(AssetEntry.quantity), 0)).where(
            AssetEntry.asset_id == asset.id
        )
    ).one()
    exits = session.exec(
        select(func.coalesce(func.sum(AssetExit.quantity), 0)).where(
            AssetExit.asset_id == asset.id
        )
    ).one()
    return AssetResponse(**asset.model_dump(), current_stock=entries - exits)


def list_inventory_products(
    session: Session,
    *,
    product_id: int | None = None,
    sku: str | None = None,
    name: str | None = None,
) -> list[AssetResponse]:
    """Read products and current stock, with optional ID/SKU/name filters."""
    statement = select(Asset)
    if product_id is not None:
        statement = statement.where(Asset.id == product_id)
    if sku is not None:
        statement = statement.where(Asset.sku.ilike(f"%{sku}%"))
    if name is not None:
        statement = statement.where(Asset.name.ilike(f"%{name}%"))
    assets = session.exec(statement.order_by(Asset.id)).all()
    return [inventory_product_response(session, asset) for asset in assets]
