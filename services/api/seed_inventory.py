import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import func
from sqlmodel import SQLModel, Session, select

from services.api.database import DEFAULT_DATABASE_PATH, engine
from services.api.models import Asset, AssetEntry, AssetExit


ASSETS_SEED = [
	("Port\u00e1til 14\" Business", "NXV-IT-001", "hardware", "Valencia"),
	("Port\u00e1til 14\" Business", "NXV-IT-002", "hardware", "Miami"),
	("Rat\u00f3n ergon\u00f3mico", "NXV-PER-001", "peripherals", "Valencia"),
	("Hub USB-C", "NXV-PER-002", "peripherals", "Miami"),
	("Resma de papel A4", "NXV-OFF-001", "office_supplies", "Valencia"),
	("Cuaderno de formaci\u00f3n en liderazgo", "NXV-TRN-001", "training_materials", "Valencia"),
]
ENTRIES_SEED = [
	("NXV-IT-001", 10, "TechDistrib Valencia S.L."),
	("NXV-IT-001", 5, "TechDistrib Valencia S.L."),
	("NXV-PER-001", 20, "TechDistrib Valencia S.L."),
	("NXV-OFF-001", 100, "Office Depot Miami"),
]
EXITS_SEED = [
	("NXV-IT-001", 2, "allocation", "Equipo IT Valencia"),
	("NXV-PER-001", 3, "allocation", "Operaciones Valencia"),
	("NXV-OFF-001", 10, "consumption", None),
]


def seed_inventory(session: Session, user_uuid: str) -> dict[str, int]:
	if not user_uuid.strip():
		raise ValueError("A TinyDB user identifier is required")
	inserted = {"assets": 0, "entries": 0, "exits": 0}
	assets = {}
	for name, sku, category, office in ASSETS_SEED:
		asset = session.exec(
			select(Asset).where(Asset.sku == sku).with_for_update()
		).first()
		if asset is None:
			asset = Asset(name=name, sku=sku, category=category, office=office)
			session.add(asset)
			session.flush()
			inserted["assets"] += 1
		elif (asset.name, asset.category, asset.office) != (name, category, office):
			raise ValueError("An existing seed SKU has conflicting asset data")
		assets[sku] = asset

	for sku, quantity, supplier in ENTRIES_SEED:
		asset = assets[sku]
		existing = session.exec(select(AssetEntry).where(
			AssetEntry.asset_id == asset.id,
			AssetEntry.quantity == quantity,
			AssetEntry.supplier == supplier,
			AssetEntry.office == asset.office,
		)).first()
		if existing is None:
			session.add(AssetEntry(
				asset_id=asset.id, quantity=quantity, supplier=supplier,
				office=asset.office, user_uuid=user_uuid,
			))
			session.flush()
			inserted["entries"] += 1

	for sku, quantity, exit_type, assigned_to in EXITS_SEED:
		asset = assets[sku]
		existing = session.exec(select(AssetExit).where(
			AssetExit.asset_id == asset.id,
			AssetExit.quantity == quantity,
			AssetExit.exit_type == exit_type,
			AssetExit.assigned_to == assigned_to,
			AssetExit.office == asset.office,
		)).first()
		if existing is not None:
			continue
		entries = session.exec(select(func.coalesce(func.sum(AssetEntry.quantity), 0))
			.where(AssetEntry.asset_id == asset.id)).one()
		exits = session.exec(select(func.coalesce(func.sum(AssetExit.quantity), 0))
			.where(AssetExit.asset_id == asset.id)).one()
		if quantity > entries - exits:
			raise ValueError("Insufficient stock for a seed exit; no changes committed")
		session.add(AssetExit(
			asset_id=asset.id, quantity=quantity, exit_type=exit_type,
			assigned_to=assigned_to, office=asset.office, user_uuid=user_uuid,
		))
		session.flush()
		inserted["exits"] += 1
	return inserted


def main() -> int:
	parser = argparse.ArgumentParser(description="Seed inventory without changing TinyDB")
	parser.add_argument("--user-id", required=True, type=int)
	args = parser.parse_args()
	try:
		path = Path(os.environ.get("SUPPLIERS_DB_PATH", str(DEFAULT_DATABASE_PATH)))
		with path.open(encoding="utf-8") as source:
			user = json.load(source).get("users", {}).get(str(args.user_id))
		if user is None or not user.get("is_active", True):
			raise ValueError("The seed requires an existing active TinyDB user")
		SQLModel.metadata.create_all(engine)
		with Session(engine) as session, session.begin():
			inserted = seed_inventory(session, str(args.user_id))
	except Exception as error:
		print(f"Inventory seed failed ({type(error).__name__}); details omitted.", file=sys.stderr)
		return 1
	print(f"Inserted: {inserted}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())