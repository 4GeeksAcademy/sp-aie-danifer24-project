from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Office = Literal["Valencia", "Miami"]
AssetCategory = Literal[
	"hardware", "peripherals", "office_supplies", "training_materials"
]


class AssetCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: NonEmptyString
	sku: NonEmptyString
	category: AssetCategory
	office: Office


class AssetResponse(AssetCreate):
	model_config = ConfigDict(from_attributes=True)

	id: int = Field(gt=0)
	current_stock: int = Field(ge=0)


class AssetEntryCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	asset_id: int = Field(gt=0, strict=True)
	quantity: int = Field(gt=0, strict=True)
	supplier: NonEmptyString
	office: Office


class AssetEntryResponse(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int = Field(gt=0)
	quantity: int = Field(gt=0)
	supplier: NonEmptyString
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