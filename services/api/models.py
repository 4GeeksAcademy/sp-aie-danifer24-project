"""Modelos Pydantic del directorio de proveedores."""

import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	StringConstraints,
	field_validator,
	model_validator,
)


class SupplierCountry(str, Enum):
	SPAIN = "Spain"
	USA = "USA"


class SupplierCurrency(str, Enum):
	EUR = "EUR"
	USD = "USD"


class SupplierStatus(str, Enum):
	ACTIVE = "active"
	SUSPENDED = "suspended"


class SupplierCategory(str, Enum):
	JOB_BOARDS = "job_boards"
	ATS_SOFTWARE = "ats_software"
	ASSESSMENT_TOOLS = "assessment_tools"
	TRAINING_PLATFORMS = "training_platforms"
	PAYROLL_AND_HR_SOFTWARE = "payroll_and_hr_software"
	VIDEO_INTERVIEW = "video_interview"
	BACKGROUND_CHECK = "background_check"
	OFFICE_AND_FACILITIES = "office_and_facilities"
	IT_AND_SOFTWARE_LICENSES = "it_and_software_licenses"


class IncidentCategory(str, Enum):
	TECHNICAL_FAILURE = "technical_failure"
	PROCESS_ERROR = "process_error"
	CLIENT_COMPLAINT = "client_complaint"
	CANDIDATE_ISSUE = "candidate_issue"
	STAFF_ISSUE = "staff_issue"
	SLA_BREACH = "sla_breach"
	DATA_QUALITY = "data_quality"
	OTHER = "other"


class IncidentStatus(str, Enum):
	OPEN = "open"
	IN_PROGRESS = "in_progress"
	RESOLVED = "resolved"
	DISCARDED = "discarded"


class IncidentOrigin(str, Enum):
	CUSTOMER = "customer"
	BRANCH = "branch"
	INTERNAL = "internal"


class IncidentBranch(str, Enum):
	CENTRAL = "central"
	VALENCIA_OPERATIONS = "valencia_operations"
	MIAMI_OFFICE = "miami_office"
	REMOTE = "remote"


class IncidentCreate(BaseModel):
	"""Datos de entrada para registrar una incidencia."""

	model_config = ConfigDict(extra="forbid")

	title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
	description: str
	category: IncidentCategory
	status: IncidentStatus
	origin: IncidentOrigin
	branch: IncidentBranch

	@field_validator("description")
	@classmethod
	def validate_description(cls, value: str) -> str:
		if not value.strip():
			raise ValueError("description must not be empty")
		return value


class Incident(IncidentCreate):
	"""Incidencia persistida; TinyDB genera el ID al insertar el registro."""

	id: int = Field(gt=0, strict=True)
	created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
	updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

	def mark_updated(self) -> None:
		"""Actualizar la marca temporal cuando se modifica una incidencia."""
		self.updated_at = datetime.now(timezone.utc)


class IncidentResponse(Incident):
	"""Representación pública de una incidencia guardada."""


class IncidentStatusUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	status: IncidentStatus


class SupplierBase(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
	country: SupplierCountry
	categories: list[SupplierCategory] = Field(min_length=1)
	monthly_rate: float = Field(gt=0, allow_inf_nan=False)
	currency: SupplierCurrency
	status: SupplierStatus
	contract_renewal_date: str | None = Field(
		default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
	)
	contact_email: str | None = None
	notes: str | None = None

	@field_validator("contract_renewal_date")
	@classmethod
	def validate_renewal_date(cls, value: str | None) -> str | None:
		if value is not None:
			date.fromisoformat(value)
		return value

	@model_validator(mode="after")
	def validate_country_currency(self) -> "SupplierBase":
		expected_currency = {
			SupplierCountry.SPAIN: SupplierCurrency.EUR,
			SupplierCountry.USA: SupplierCurrency.USD,
		}[self.country]
		if self.currency != expected_currency:
			raise ValueError(
				f"currency must be {expected_currency.value} for {self.country.value}"
			)
		return self


class SupplierCreate(SupplierBase):
	pass


class Supplier(SupplierBase):
	updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SupplierResponse(Supplier):
	id: int = Field(gt=0, strict=True)


class SupplierRateUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	monthly_rate: float = Field(gt=0, allow_inf_nan=False)


class SupplierStatusUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	status: SupplierStatus


class UserRole(str, Enum):
	ADMIN = "admin"
	MANAGER = "manager"
	USER = "user"


class User(BaseModel):
	model_config = ConfigDict(extra="forbid")

	id: int = Field(gt=0, strict=True)
	email: str
	hashed_password: str
	is_active: bool = True
	role: UserRole = UserRole.USER
	created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Profile(BaseModel):
	model_config = ConfigDict(extra="forbid")

	id: int = Field(gt=0, strict=True)
	user_id: int = Field(gt=0, strict=True)
	name: str | None = None
	phone: str | None = None
	address: str | None = None


class ProfileUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str | None = None
	phone: str | None = None
	address: str | None = None

	@model_validator(mode="after")
	def validate_changes(self) -> "ProfileUpdate":
		if not self.model_fields_set:
			raise ValueError("provide at least one profile field to update")
		return self


class UserCreate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3)]
	password: Annotated[str, StringConstraints(min_length=8)]
	name: str | None = None
	phone: str | None = None
	address: str | None = None

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str) -> str:
		value = value.strip()
		value = value.lower()
		if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
			raise ValueError("email must be a valid email address")
		return value

	@field_validator("password")
	@classmethod
	def validate_password_length(cls, value: str) -> str:
		if len(value.encode("utf-8")) > 72:
			raise ValueError("password must not exceed 72 UTF-8 bytes")
		return value


class UserUpdate(BaseModel):
	model_config = ConfigDict(extra="forbid")

	email: str | None = None
	password: Annotated[str, StringConstraints(min_length=8)] | None = None
	role: UserRole | None = None
	is_active: bool | None = None

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str | None) -> str | None:
		if value is None:
			return value
		value = value.strip().lower()
		if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
			raise ValueError("email must be a valid email address")
		return value

	@field_validator("password")
	@classmethod
	def validate_password_length(cls, value: str | None) -> str | None:
		if value is not None and len(value.encode("utf-8")) > 72:
			raise ValueError("password must not exceed 72 UTF-8 bytes")
		return value

	@model_validator(mode="after")
	def validate_changes(self) -> "UserUpdate":
		if not self.model_fields_set or any(
			getattr(self, field) is None for field in self.model_fields_set
		):
			raise ValueError("provide at least one non-null field to update")
		return self


class UserResponse(BaseModel):
	id: int
	email: str
	is_active: bool
	role: UserRole
	created_at: datetime


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"


class LoginRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	email: str
	password: str

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str) -> str:
		value = value.strip().lower()
		if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
			raise ValueError("email must be a valid email address")
		return value


class AuthMeResponse(BaseModel):
	email: str
	role: UserRole
	profile: Profile


class ForgotPasswordRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")
	email: str


class NewPasswordRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")
	new_password: Annotated[str, StringConstraints(min_length=8)]

	@field_validator("new_password")
	@classmethod
	def validate_new_password(cls, value: str) -> str:
		if len(value.encode("utf-8")) > 72:
			raise ValueError("password must not exceed 72 UTF-8 bytes")
		return value


class ResetPasswordRequest(NewPasswordRequest):
	token: str


class ChangePasswordRequest(NewPasswordRequest):
	current_password: str