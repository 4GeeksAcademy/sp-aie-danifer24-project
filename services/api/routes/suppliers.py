"""Endpoints del directorio de proveedores."""

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from tinydb import Query
from tinydb.table import Table

from services.api.database import database_lock, get_database
from services.api.models import (
	Supplier,
	SupplierCategory,
	SupplierCountry,
	SupplierCreate,
	SupplierRateUpdate,
	SupplierResponse,
	SupplierStatusUpdate,
)


router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def get_suppliers_table() -> Iterator[Table]:
	with database_lock:
		with get_database() as database:
			yield database.table("suppliers")


SuppliersTable = Annotated[Table, Depends(get_suppliers_table)]
SupplierId = Annotated[int, Path(gt=0)]


def get_supplier(table: Table, supplier_id: int) -> SupplierResponse:
	document = table.get(doc_id=supplier_id)
	if document is None:
		raise HTTPException(status_code=404, detail="Proveedor no encontrado")
	return SupplierResponse(**document, id=document.doc_id)


@router.post("", response_model=SupplierResponse, status_code=201)
def create_supplier(request: SupplierCreate, table: SuppliersTable):
	supplier = Supplier(**request.model_dump())
	document = supplier.model_dump(mode="json")
	supplier_id = table.insert(document)
	return SupplierResponse(**document, id=supplier_id)


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(
	table: SuppliersTable,
	country: SupplierCountry | None = None,
	category: SupplierCategory | None = None,
):
	query = Query()
	filters = query.noop()
	if country is not None:
		filters &= query.country == country.value
	if category is not None:
		filters &= query.categories.any([category.value])
	return [
		SupplierResponse(**document, id=document.doc_id)
		for document in table.search(filters)
	]


@router.get("/{id}", response_model=SupplierResponse)
def retrieve_supplier(id: SupplierId, table: SuppliersTable):
	return get_supplier(table, id)


@router.patch("/{id}/rate", response_model=SupplierResponse)
def update_supplier_rate(id: SupplierId, request: SupplierRateUpdate, table: SuppliersTable):
	supplier = get_supplier(table, id)
	if request.monthly_rate != supplier.monthly_rate:
		table.update(
			{
				"monthly_rate": request.monthly_rate,
				"updated_at": datetime.now(timezone.utc).isoformat(),
			},
			doc_ids=[id],
		)
	return get_supplier(table, id)


@router.patch("/{id}/status", response_model=SupplierResponse)
def update_supplier_status(id: SupplierId, request: SupplierStatusUpdate, table: SuppliersTable):
	get_supplier(table, id)
	table.update({"status": request.status.value}, doc_ids=[id])
	return get_supplier(table, id)


@router.delete("/{id}", status_code=204)
def delete_supplier(id: SupplierId, table: SuppliersTable):
	get_supplier(table, id)
	table.remove(doc_ids=[id])
	return Response(status_code=204)