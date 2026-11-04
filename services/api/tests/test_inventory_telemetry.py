from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool

from services.api.database import get_db
from services.api.models import Asset, AssetEntry
from services.api.security import create_access_token
from services.api.main import app


def make_inventory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_asset_telemetry_metadata_and_inbound_order_validate_and_persist(api, register):
    client, tables, _ = api
    register(client)
    user_id = tables[0].all()[0].doc_id
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    catalog = client.get("/inventory/programmes")
    assert catalog.status_code == 200
    assert catalog.json() == [
        {"id": "ventas-b2b", "name": "Formación en ventas B2B"},
        {"id": "liderazgo-basico", "name": "Liderazgo básico"},
        {"id": "onboarding-soporte", "name": "Onboarding de soporte"},
    ]
    engine = make_inventory_engine()
    asset_id = None
    tables[2].insert({"name": "Proveedor EU", "currency": "EUR", "status": "active"})

    with Session(engine) as session:
        asset = Asset(name="Kit", sku="TEST-KIT-1", category="training_materials", office="Valencia")
        session.add(asset)
        session.commit()
        session.refresh(asset)
        asset_id = asset.id

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        updated = client.patch(
            f"/inventory/products/{asset_id}/telemetry-metadata",
            headers=headers,
            json={"product_category": "training_kit", "programme_id": "ventas-b2b"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["product_category"] == "training_kit"
        assert updated.json()["programme_id"] == "ventas-b2b"

        invalid_programme = client.patch(
            f"/inventory/products/{asset_id}/telemetry-metadata",
            headers=headers,
            json={"product_category": "training_kit", "programme_id": "ventas-21234"},
        )
        assert invalid_programme.status_code == 422

        created = client.post(
            "/inventory/orders/inbound",
            headers=headers,
            json={"asset_id": asset_id, "quantity": 3, "supplier_id": 1, "unit_cost": 19.5, "office": "Valencia"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["supplier_id"] == 1
        assert created.json()["unit_cost"] == 19.5

        mismatch = client.post(
            "/inventory/orders/inbound",
            headers=headers,
            json={"asset_id": asset_id, "quantity": 1, "supplier_id": 1, "unit_cost": 19.5, "office": "Miami"},
        )
        assert mismatch.status_code == 400

        with Session(engine) as session:
            entries = session.exec(select(AssetEntry)).all()
            assert len(entries) == 1
            assert entries[0].supplier == "Proveedor EU"
            assert entries[0].supplier_id == 1
            assert entries[0].unit_cost == 19.5
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()