"""Generate a deterministic, repeatable inventory dataset for performance testing."""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, SQLModel, select

from services.api.database import engine
from services.api.models import Asset, AssetEntry, AssetExit


SEED_PREFIX = "caching-seed-v1"
BASE_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
CATEGORIES = ("hardware", "peripherals", "office_supplies", "training_materials")
OFFICES = ("Valencia", "Miami")
SUPPLIERS = (
    "TechDistrib Valencia S.L.",
    "Office Depot Miami",
    "Nexova IT Procurement",
    "Formación Levante",
    "Atlantic Business Supply",
)
EXIT_ASSIGNEES = (
    "Equipo de selección Valencia",
    "Operaciones Miami",
    "Formación corporativa",
    "Equipo de tecnología",
)
MAX_PRODUCTS = 10_000
MAX_MOVEMENTS = 50_000


def asset_data(index: int) -> dict[str, str]:
    category = CATEGORIES[index % len(CATEGORIES)]
    office = OFFICES[index % len(OFFICES)]
    names = {
        "hardware": ("Portátil empresarial", "Monitor profesional", "Estación de trabajo"),
        "peripherals": ("Ratón ergonómico", "Teclado inalámbrico", "Hub USB-C"),
        "office_supplies": ("Resma de papel A4", "Cuaderno de reuniones", "Kit de escritura"),
        "training_materials": ("Manual de liderazgo", "Kit de formación", "Guía de entrevistas"),
    }
    name = names[category][(index // len(CATEGORIES)) % len(names[category])]
    return {
        "name": f"{name} {index + 1:05d}",
        "sku": f"CACHE-{index + 1:05d}",
        "category": category,
        "office": office,
    }


def validate_counts(products: int, entries_per_product: int, exits_per_product: int) -> None:
    if not 1 <= products <= MAX_PRODUCTS:
        raise ValueError(f"products must be between 1 and {MAX_PRODUCTS}")
    if not 1 <= entries_per_product <= 10:
        raise ValueError("entries-per-product must be between 1 and 10")
    if not 0 <= exits_per_product <= 10:
        raise ValueError("exits-per-product must be between 0 and 10")
    total_movements = products * (entries_per_product + exits_per_product)
    if total_movements > MAX_MOVEMENTS:
        raise ValueError(f"the requested dataset exceeds {MAX_MOVEMENTS} movements")


def same_datetime(actual: datetime, expected: datetime) -> bool:
    """Compare SQL timestamps consistently across timezone-aware and naive drivers."""
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=timezone.utc)
    return actual.astimezone(timezone.utc) == expected.astimezone(timezone.utc)


def seed_performance_data(
    session: Session,
    products: int = 1_000,
    entries_per_product: int = 3,
    exits_per_product: int = 2,
) -> dict[str, int]:
    """Insert deterministic assets and movements, preserving unrelated records."""
    validate_counts(products, entries_per_product, exits_per_product)
    inserted = {"assets": 0, "entries": 0, "exits": 0}
    expected_assets = [asset_data(index) for index in range(products)]
    skus = [item["sku"] for item in expected_assets]
    existing_assets = {
        asset.sku: asset
        for asset in session.exec(select(Asset).where(Asset.sku.in_(skus))).all()
    }

    assets_by_sku: dict[str, Asset] = {}
    for expected in expected_assets:
        asset = existing_assets.get(expected["sku"])
        if asset is None:
            asset = Asset(**expected)
            session.add(asset)
            session.flush()
            inserted["assets"] += 1
        elif any(getattr(asset, key) != value for key, value in expected.items()):
            raise ValueError(f"Existing asset {expected['sku']} conflicts with performance seed")
        assets_by_sku[expected["sku"]] = asset

    entry_ids = [
        f"{SEED_PREFIX}:entry:{asset['sku']}:{movement}"
        for asset in expected_assets
        for movement in range(entries_per_product)
    ]
    exit_ids = [
        f"{SEED_PREFIX}:exit:{asset['sku']}:{movement}"
        for asset in expected_assets
        for movement in range(exits_per_product)
    ]
    existing_entries = {
        record.user_uuid: record
        for record in session.exec(
            select(AssetEntry).where(AssetEntry.user_uuid.in_(entry_ids))
        ).all()
    } if entry_ids else {}
    existing_exits = {
        record.user_uuid: record
        for record in session.exec(
            select(AssetExit).where(AssetExit.user_uuid.in_(exit_ids))
        ).all()
    } if exit_ids else {}

    for index, expected_asset in enumerate(expected_assets):
        asset = assets_by_sku[expected_asset["sku"]]
        available_stock = 0
        for movement in range(entries_per_product):
            seed_id = f"{SEED_PREFIX}:entry:{asset.sku}:{movement}"
            quantity = 100 + ((index * 17 + movement * 13) % 101)
            supplier = SUPPLIERS[(index + movement) % len(SUPPLIERS)]
            office = asset.office
            created_at = BASE_DATE + timedelta(days=(index * 3 + movement * 11) % 900)
            existing = existing_entries.get(seed_id)
            if existing is not None:
                expected_values = (asset.id, quantity, supplier, office, created_at)
                actual_values = (
                    existing.asset_id,
                    existing.quantity,
                    existing.supplier,
                    existing.office,
                    existing.created_at,
                )
                if (
                    actual_values[:4] != expected_values[:4]
                    or not same_datetime(actual_values[4], expected_values[4])
                ):
                    raise ValueError(f"Existing seeded entry {seed_id} conflicts with performance seed")
            else:
                session.add(AssetEntry(
                    asset_id=asset.id,
                    quantity=quantity,
                    supplier=supplier,
                    office=office,
                    created_at=created_at,
                    user_uuid=seed_id,
                ))
                inserted["entries"] += 1
            available_stock += quantity

        for movement in range(exits_per_product):
            seed_id = f"{SEED_PREFIX}:exit:{asset.sku}:{movement}"
            quantity = 1 + ((index * 5 + movement * 7) % 5)
            exit_type = "allocation" if movement % 2 == 0 else "consumption"
            assigned_to = (
                EXIT_ASSIGNEES[(index + movement) % len(EXIT_ASSIGNEES)]
                if exit_type == "allocation"
                else None
            )
            office = asset.office
            created_at = BASE_DATE + timedelta(days=(index * 5 + movement * 17) % 900)
            if quantity > available_stock:
                raise ValueError(f"Insufficient seed stock for {asset.sku}")
            existing = existing_exits.get(seed_id)
            if existing is not None:
                expected_values = (
                    asset.id, quantity, exit_type, assigned_to, office, created_at
                )
                actual_values = (
                    existing.asset_id,
                    existing.quantity,
                    existing.exit_type,
                    existing.assigned_to,
                    existing.office,
                    existing.created_at,
                )
                if (
                    actual_values[:5] != expected_values[:5]
                    or not same_datetime(actual_values[5], expected_values[5])
                ):
                    raise ValueError(f"Existing seeded exit {seed_id} conflicts with performance seed")
            else:
                session.add(AssetExit(
                    asset_id=asset.id,
                    quantity=quantity,
                    exit_type=exit_type,
                    assigned_to=assigned_to,
                    office=office,
                    created_at=created_at,
                    user_uuid=seed_id,
                ))
                inserted["exits"] += 1
            available_stock -= quantity

    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed realistic inventory rows for local performance measurements"
    )
    parser.add_argument("--products", type=int, default=1_000)
    parser.add_argument("--entries-per-product", type=int, default=3)
    parser.add_argument("--exits-per-product", type=int, default=2)
    args = parser.parse_args()

    try:
        validate_counts(args.products, args.entries_per_product, args.exits_per_product)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            inserted = seed_performance_data(
                session,
                products=args.products,
                entries_per_product=args.entries_per_product,
                exits_per_product=args.exits_per_product,
            )
    except Exception as error:
        print(
            f"Performance seed failed ({type(error).__name__}); details omitted.",
            file=sys.stderr,
        )
        return 1
    print(f"Inserted: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
