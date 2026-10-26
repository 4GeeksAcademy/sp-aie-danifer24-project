from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from services.api.dependencies import DatabaseSession
from services.api.models import Asset, AssetEntry, AssetExit
from services.api.schemas import (
	AssetCreate,
	AssetEntryCreate,
	AssetEntryOrderResponse,
	AssetEntryResponse,
	AssetExitCreate,
	AssetExitOrderResponse,
	AssetExitResponse,
	AssetResponse,
)
from services.api.security import CurrentUser


router = APIRouter(prefix="/inventory", tags=["inventory"])
AssetId = Annotated[int, Path(gt=0)]


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


@router.get("/products", response_model=list[AssetResponse])
def list_products(session: DatabaseSession):
	return [
		asset_response(session, asset)
		for asset in session.exec(select(Asset).order_by(Asset.id)).all()
	]


@router.post("/products", response_model=AssetResponse, status_code=201)
def create_product(request: AssetCreate, current_user: CurrentUser, session: DatabaseSession):
	asset = Asset(**request.model_dump())
	session.add(asset)
	try:
		session.commit()
	except IntegrityError:
		session.rollback()
		raise HTTPException(status_code=409, detail="Asset SKU already exists") from None
	session.refresh(asset)
	return asset_response(session, asset)


@router.get("/products/{id}", response_model=AssetResponse)
def retrieve_product(id: AssetId, session: DatabaseSession):
	return asset_response(session, get_asset(session, id))


@router.post("/orders/inbound", response_model=AssetEntryResponse, status_code=201)
def create_entry(request: AssetEntryCreate, current_user: CurrentUser, session: DatabaseSession):
	get_asset(session, request.asset_id, lock=True)
	entry = AssetEntry(**request.model_dump(), user_uuid=str(current_user.id))
	session.add(entry)
	session.commit()
	session.refresh(entry)
	return entry


@router.post("/orders/outbound", response_model=AssetExitResponse, status_code=201)
def create_exit(request: AssetExitCreate, current_user: CurrentUser, session: DatabaseSession):
	asset = get_asset(session, request.asset_id, lock=True)
	available = asset_response(session, asset).current_stock
	if request.quantity > available:
		raise HTTPException(
			status_code=400,
			detail=f"Insufficient stock for asset '{asset.name}'. Available: {available}, requested: {request.quantity}.",
		)
	exit_order = AssetExit(**request.model_dump(), user_uuid=str(current_user.id))
	session.add(exit_order)
	session.commit()
	session.refresh(exit_order)
	return exit_order


@router.get("/orders", response_model=list[AssetEntryOrderResponse | AssetExitOrderResponse])
def list_orders(current_user: CurrentUser, session: DatabaseSession):
	assets = {asset.id: asset for asset in list_products(session)}
	orders = [
		AssetEntryOrderResponse(**entry.model_dump(), asset=assets[entry.asset_id])
		for entry in session.exec(select(AssetEntry)).all()
	]
	orders.extend(
		AssetExitOrderResponse(**exit_order.model_dump(), asset=assets[exit_order.asset_id])
		for exit_order in session.exec(select(AssetExit)).all()
	)
	return sorted(orders, key=lambda order: (order.created_at, order.order_type, order.id))