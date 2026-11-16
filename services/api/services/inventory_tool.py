"""Read-only, typed support tool for live inventory stock."""

from enum import Enum
from threading import Thread

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlmodel import Session

from services.api.database import engine
from services.api.schemas import AssetResponse
from services.api.services.inventory import list_inventory_products

INVENTORY_TOOL_TIMEOUT_SECONDS = 5
INVENTORY_TOOL_FALLBACK = "No pude confirmar el stock del producto ahora mismo."


class InventoryLookupInput(BaseModel):
    """Identify a live product by database ID, SKU, or product name."""

    model_config = ConfigDict(extra="forbid")

    product_id: int | None = Field(default=None, gt=0)
    sku: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)

    @field_validator("sku", "name")
    @classmethod
    def strip_search_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @model_validator(mode="after")
    def require_product_filter(self) -> "InventoryLookupInput":
        if not any((self.product_id, self.sku, self.name)):
            raise ValueError("Provide a product ID, SKU, or name; unbounded stock queries are not allowed")
        return self


class InventoryToolOutcome(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


class InventoryLookupOutput(BaseModel):
    outcome: InventoryToolOutcome
    products: list[AssetResponse] = Field(default_factory=list)
    message: str | None = None


def _query_inventory(request: InventoryLookupInput) -> InventoryLookupOutput:
    # Use the inventory's existing PostgreSQL engine and read-only product query.
    with Session(engine) as session:
        products = list_inventory_products(
            session,
            product_id=request.product_id,
            sku=request.sku,
            name=request.name,
        )
    if not products:
        return InventoryLookupOutput(
            outcome=InventoryToolOutcome.NOT_FOUND,
            message="No encontré un producto que coincida con la consulta.",
        )
    return InventoryLookupOutput(outcome=InventoryToolOutcome.FOUND, products=products)


def lookup_inventory(request: InventoryLookupInput) -> InventoryLookupOutput:
    """Read the live inventory service with a bounded timeout and safe fallbacks."""
    result: list[InventoryLookupOutput] = []
    failure: list[BaseException] = []

    def run_query() -> None:
        try:
            result.append(_query_inventory(request))
        except BaseException as exc:
            failure.append(exc)

    worker = Thread(target=run_query, name="inventory-read-tool", daemon=True)
    worker.start()
    worker.join(INVENTORY_TOOL_TIMEOUT_SECONDS)
    if worker.is_alive() or failure or not result:
        return InventoryLookupOutput(
            outcome=InventoryToolOutcome.ERROR,
            message=INVENTORY_TOOL_FALLBACK,
        )
    return result[0]
