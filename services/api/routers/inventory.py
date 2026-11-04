from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from services.api.cache import TTLCache
from services.api.dependencies import DatabaseSession, RequestTables
from services.api.models import Asset, AssetEntry, AssetExit
from services.api.inventory_catalog import INVENTORY_PROGRAMMES, INVENTORY_PROGRAMME_IDS
from services.api.schemas import (
	AssetCreate,
	AssetEntryCreate,
	AssetEntryOrderResponse,
	AssetEntryResponse,
	AssetExitCreate,
	AssetExitOrderResponse,
	AssetExitResponse,
	AssetResponse,
	AssetTelemetryMetadataUpdate,
)
from services.api.security import CurrentUser


router = APIRouter(prefix="/inventory", tags=["inventory"])
AssetId = Annotated[int, Path(gt=0)]
PRODUCTS_CACHE_TTL_SECONDS = 5
products_cache: TTLCache[str, list[AssetResponse]] = TTLCache(
	PRODUCTS_CACHE_TTL_SECONDS,
	max_entries=1,
)

def invalidate_products_cache() -> None:
	products_cache.clear()


def asset_response(session: Session, asset: Asset) -> AssetResponse:
	entries = session.exec(
		select(func.coalesce(func.sum(AssetEntry.quantity), 0))
		.where(AssetEntry.asset_id == asset.id)
	).one()
	exits = session.exec(
		select(func.coalesce(func.sum(AssetExit.quantity), 0))
		.where(AssetExit.asset_id == asset.id)
	).one()
	return AssetResponse(**asset.model_dump(), current_stock=entries - exits)


def get_asset(session: Session, asset_id: int, lock: bool = False) -> Asset:
	statement = select(Asset).where(Asset.id == asset_id)
	if lock:
		statement = statement.with_for_update()
	asset = session.exec(statement).first()
	if asset is None:
		raise HTTPException(status_code=404, detail="Asset not found")
	return asset


@router.get("/programmes")
def list_programmes():
	return list(INVENTORY_PROGRAMMES)


@router.get("/products", response_model=list[AssetResponse])
def list_products(session: DatabaseSession):
	generation = products_cache.generation()
	cached = products_cache.get("all")
	if cached is not None:
		return cached
	response = [
		asset_response(session, asset)
		for asset in session.exec(select(Asset).order_by(Asset.id)).all()
	]
	products_cache.set("all", response, generation)
	return response


@router.post("/products", response_model=AssetResponse, status_code=201)
def create_product(request: AssetCreate, current_user: CurrentUser, session: DatabaseSession):
	asset = Asset(**request.model_dump())
	session.add(asset)
	try:
		session.commit()
	except IntegrityError:
		session.rollback()
		raise HTTPException(status_code=409, detail="Asset SKU already exists") from None
	invalidate_products_cache()
	session.refresh(asset)
	return asset_response(session, asset)


@router.patch("/products/{id}/telemetry-metadata", response_model=AssetResponse)
def update_product_telemetry_metadata(
	id: AssetId,
	request: AssetTelemetryMetadataUpdate,
	current_user: CurrentUser,
	session: DatabaseSession,
):
	if request.programme_id not in INVENTORY_PROGRAMME_IDS:
		raise HTTPException(status_code=422, detail="Programme is not in the inventory catalog")
	asset = get_asset(session, id, lock=True)
	asset.product_category = request.product_category
	asset.programme_id = request.programme_id
	session.add(asset)
	session.commit()
	invalidate_products_cache()
	session.refresh(asset)
	return asset_response(session, asset)


@router.get("/products/{id}", response_model=AssetResponse)
def retrieve_product(id: AssetId, session: DatabaseSession):
	return asset_response(session, get_asset(session, id))


@router.post("/orders/inbound", response_model=AssetEntryResponse, status_code=201)
def create_entry(
	request: AssetEntryCreate,
	current_user: CurrentUser,
	session: DatabaseSession,
	tables: RequestTables,
):
	asset = get_asset(session, request.asset_id, lock=True)
	if request.office != asset.office:
		raise HTTPException(status_code=400, detail="Order office does not match the asset office")
	supplier_document = tables[2].get(doc_id=request.supplier_id)
	if supplier_document is None or supplier_document.get("status") != "active":
		raise HTTPException(status_code=404, detail="Active supplier not found")
	expected_currency = "EUR" if asset.office == "Valencia" else "USD"
	if supplier_document.get("currency") != expected_currency:
		raise HTTPException(status_code=400, detail="Supplier currency does not match the asset office")
	entry = AssetEntry(
		asset_id=request.asset_id,
		quantity=request.quantity,
		supplier=supplier_document["name"],
		supplier_id=request.supplier_id,
		unit_cost=request.unit_cost,
		office=request.office,
		user_uuid=str(current_user.id),
	)
	session.add(entry)
	session.commit()
	invalidate_products_cache()
	session.refresh(entry)
	return entry


@router.post("/orders/outbound", response_model=AssetExitResponse, status_code=201)
def create_exit(request: AssetExitCreate, current_user: CurrentUser, session: DatabaseSession):
	asset = get_asset(session, request.asset_id, lock=True)
	if request.office != asset.office:
		raise HTTPException(status_code=400, detail="Order office does not match the asset office")
	available = asset_response(session, asset).current_stock
	if request.quantity > available:
		raise HTTPException(
			status_code=400,
			detail=f"Insufficient stock for asset '{asset.name}'. Available: {available}, requested: {request.quantity}.",
		)
	exit_order = AssetExit(**request.model_dump(), user_uuid=str(current_user.id))
	session.add(exit_order)
	session.commit()
	invalidate_products_cache()
	session.refresh(exit_order)
	return exit_order


@router.get("/orders", response_model=list[AssetEntryOrderResponse | AssetExitOrderResponse])
def list_orders(current_user: CurrentUser, session: DatabaseSession):
	assets = {asset.id: asset for asset in session.exec(select(Asset)).all()}
	orders = [
		AssetEntryOrderResponse(
			id=entry.id,
			quantity=entry.quantity,
			created_at=entry.created_at,
			supplier=entry.supplier,
			asset_name=assets[entry.asset_id].name,
			asset_sku=assets[entry.asset_id].sku,
		)
		for entry in session.exec(select(AssetEntry)).all()
	]
	orders.extend(
		AssetExitOrderResponse(
			id=exit_order.id,
			quantity=exit_order.quantity,
			created_at=exit_order.created_at,
			exit_type=exit_order.exit_type,
			assigned_to=exit_order.assigned_to,
			asset_name=assets[exit_order.asset_id].name,
			asset_sku=assets[exit_order.asset_id].sku,
		)
		for exit_order in session.exec(select(AssetExit)).all()
	)
	return sorted(orders, key=lambda order: (order.created_at, order.order_type, order.id))