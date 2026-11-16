import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from services.api.models import Asset, AssetEntry, AssetExit
from services.api.schemas import AssetResponse
from services.api.services import inventory_tool
from services.api.services.inventory_tool import (
    INVENTORY_TOOL_FALLBACK,
    InventoryLookupInput,
    InventoryToolOutcome,
    lookup_inventory,
)


def make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_inventory_lookup_reads_live_product_and_calculated_stock(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(inventory_tool, "engine", engine)
    try:
        with Session(engine) as session:
            asset = Asset(name="Kit de soporte", sku="SUP-KIT-1", category="training_materials", office="Valencia")
            session.add(asset)
            session.commit()
            session.refresh(asset)
            session.add(AssetEntry(asset_id=asset.id, quantity=12, supplier="Supplier", office="Valencia", user_uuid="user"))
            session.add(AssetExit(asset_id=asset.id, quantity=3, exit_type="consumption", assigned_to=None, office="Valencia", user_uuid="user"))
            session.commit()

        result = lookup_inventory(InventoryLookupInput(sku="SUP-KIT"))
        assert result.outcome == InventoryToolOutcome.FOUND
        assert len(result.products) == 1
        assert result.products[0].name == "Kit de soporte"
        assert result.products[0].current_stock == 9
        assert isinstance(result.products[0], AssetResponse)
    finally:
        engine.dispose()


def test_inventory_lookup_returns_not_found_without_inventing_stock(monkeypatch):
    engine = make_engine()
    monkeypatch.setattr(inventory_tool, "engine", engine)
    try:
        result = lookup_inventory(InventoryLookupInput(name="Producto inexistente"))
        assert result.outcome == InventoryToolOutcome.NOT_FOUND
        assert result.products == []
        assert "No encontré" in result.message
    finally:
        engine.dispose()


def test_inventory_lookup_has_bounded_timeout_and_honest_fallback(monkeypatch):
    monkeypatch.setattr(inventory_tool, "INVENTORY_TOOL_TIMEOUT_SECONDS", 0.01)
    def slow_query(request):
        import time
        time.sleep(0.1)
        return None
    monkeypatch.setattr(inventory_tool, "_query_inventory", slow_query)
    result = lookup_inventory(InventoryLookupInput(product_id=1))
    assert result.outcome == InventoryToolOutcome.ERROR
    assert result.message == INVENTORY_TOOL_FALLBACK
    assert "unidades" not in result.message


def test_inventory_lookup_converts_database_errors_to_safe_fallback(monkeypatch):
    monkeypatch.setattr(inventory_tool, "_query_inventory", lambda request: (_ for _ in ()).throw(RuntimeError("db secret")))
    result = lookup_inventory(InventoryLookupInput(product_id=1))
    assert result.outcome == InventoryToolOutcome.ERROR
    assert result.message == INVENTORY_TOOL_FALLBACK


@pytest.mark.parametrize("payload", [{}, {"name": " "}, {"product_id": 0}])
def test_inventory_lookup_requires_a_specific_valid_product_filter(payload):
    with pytest.raises(ValueError):
        InventoryLookupInput(**payload)
