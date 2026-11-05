"""Response and request schemas for weekly business reporting endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


PipelineStatus = Literal["Running", "Completed", "Failed"]
Office = Literal["valencia", "miami"]
Currency = Literal["EUR", "USD"]


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    flow_run_id: str
    flow_name: str
    status: PipelineStatus
    week_start: date
    started_at: datetime
    ended_at: datetime | None
    processed_records: int
    accepted_records: int
    rejected_records: int
    rows_written: int
    error_code: str | None
    error_message: str | None


class StartPipelineRunRequest(BaseModel):
    week_start: date | None = None


class StartPipelineRunResponse(BaseModel):
    run_id: str
    flow_run_id: str
    status: Literal["Running"]
    week_start: date


class WeeklyKPIEntry(BaseModel):
    office: Office
    programme_id: str
    total_material_cost: Decimal
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: Currency

    @field_serializer("total_material_cost")
    def serialize_total_material_cost(self, value: Decimal) -> float:
        """Keep the briefing's JSON number representation for monetary KPIs."""
        return float(value)


class WeeklyKPIResponse(BaseModel):
    week_start: date
    entries: list[WeeklyKPIEntry] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    code: str
    status_code: int
