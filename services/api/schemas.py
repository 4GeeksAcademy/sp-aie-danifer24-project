from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator, model_validator
from services.api.inventory_catalog import BUSINESS_PRODUCT_CATEGORIES, INVENTORY_PROGRAMME_IDS


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Office = Literal["Valencia", "Miami"]
AssetCategory = Literal[
	"hardware", "peripherals", "office_supplies", "training_materials"
]
BusinessProductCategory = Literal.__getitem__(tuple(BUSINESS_PRODUCT_CATEGORIES))
ProgrammeId = Literal.__getitem__(INVENTORY_PROGRAMME_IDS)


TelemetryUUID = Annotated[str, StringConstraints(
	pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
)]
TelemetryUserId = Annotated[str, StringConstraints(pattern=r"^u1_[a-f0-9]{64}$")]
TelemetryTimestamp = Annotated[str, StringConstraints(
	pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$",
)]


class TelemetryEvent(BaseModel):
	model_config = ConfigDict(extra="forbid")

	eventId: TelemetryUUID
	timestamp: TelemetryTimestamp
	sessionId: TelemetryUUID | None
	userId: TelemetryUserId | None
	event_type: Annotated[str, StringConstraints(pattern=r"^[a-z]+(?:_[a-z]+)+$", max_length=128)]
	schemaVersion: Literal["1.0.0"]
	requestId: TelemetryUUID
	properties: dict[str, JsonValue]

	@field_validator("timestamp")
	@classmethod
	def validate_timestamp(cls, value: str) -> str:
		datetime.fromisoformat(value.replace("Z", "+00:00"))
		return value
class TelemetryBatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	events: list[JsonValue] = Field(max_length=50)


class TelemetryReceipt(BaseModel):
	received: int = Field(ge=0)
	stored: int = Field(ge=0)
	rejected: int = Field(ge=0)


class AssetCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: NonEmptyString
	sku: NonEmptyString
	category: AssetCategory
	office: Office
	product_category: BusinessProductCategory | None = None
	programme_id: ProgrammeId | None = None


class AssetResponse(AssetCreate):
	model_config = ConfigDict(from_attributes=True)

	id: int = Field(gt=0)
	current_stock: int = Field(ge=0)


class AssetTelemetryMetadataUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	product_category: BusinessProductCategory
	programme_id: ProgrammeId


class AssetEntryCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	asset_id: int = Field(gt=0, strict=True)
	quantity: int = Field(gt=0, strict=True)
	supplier_id: int = Field(gt=0, strict=True)
	unit_cost: float = Field(ge=0, allow_inf_nan=False)
	office: Office


class AssetEntryResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int = Field(gt=0)
	quantity: int = Field(gt=0)
	supplier: NonEmptyString
	supplier_id: int | None = Field(default=None, gt=0)
	unit_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
	office: Office
	created_at: datetime


class AssetExitCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	asset_id: int = Field(gt=0, strict=True)
	quantity: int = Field(gt=0, strict=True)
	exit_type: Literal["allocation", "consumption"]
	assigned_to: NonEmptyString | None = None
	office: Office

	@model_validator(mode="after")
	def validate_assigned_to(self) -> "AssetExitCreate":
		if self.exit_type == "allocation" and self.assigned_to is None:
			raise ValueError("assigned_to is required for allocation")
		if self.exit_type == "consumption" and self.assigned_to is not None:
			raise ValueError("assigned_to must be null for consumption")
		return self


class AssetExitResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int = Field(gt=0)
	quantity: int = Field(gt=0)
	exit_type: Literal["allocation", "consumption"]
	assigned_to: NonEmptyString | None = None
	office: Office
	created_at: datetime


class AssetEntryOrderResponse(BaseModel):
	id: int = Field(gt=0)
	quantity: int = Field(gt=0)
	created_at: datetime
	supplier: NonEmptyString
	order_type: Literal["inbound"] = "inbound"
	asset_name: NonEmptyString
	asset_sku: NonEmptyString


class AssetExitOrderResponse(BaseModel):
	id: int = Field(gt=0)
	quantity: int = Field(gt=0)
	created_at: datetime
	exit_type: Literal["allocation", "consumption"]
	assigned_to: NonEmptyString | None = None
	order_type: Literal["outbound"] = "outbound"
	asset_name: NonEmptyString
	asset_sku: NonEmptyString