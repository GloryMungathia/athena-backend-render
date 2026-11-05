import re
import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from models.business import (
    ApprovalStatus,
    BusinessRole,
    BusinessType,
    PayoutNetwork,
    SupplierKind,
)
from models.listing import Stream
from schemas.common import clean_text
from schemas.locations import LocationCreate, LocationRead, LocationSummary

_PHONE = re.compile(r"^\+?\d{9,15}$")
_KENYA_MOBILE = re.compile(r"^(?:\+?254|0)?([17]\d{8})$")


def normalise_phone(value: str) -> str:
    digits = re.sub(r"[\s\-()]", "", value)
    if not _PHONE.match(digits):
        raise ValueError("enter a valid phone number")
    kenya = _KENYA_MOBILE.match(digits)
    if kenya:
        return f"+254{kenya.group(1)}"
    if digits.startswith("0"):
        return f"+254{digits[1:]}"
    return digits if digits.startswith("+") else f"+{digits}"


def normalise_mpesa_phone(value: str) -> str:
    digits = re.sub(r"[\s\-()]", "", value)
    match = _KENYA_MOBILE.match(digits)
    if not match:
        raise ValueError("enter an M-Pesa number, for example 0712 345 678")
    return f"+254{match.group(1)}"


def unique_streams(value: list[Stream]) -> list[Stream]:
    return list(dict.fromkeys(value))


class _BusinessRules(BaseModel):
    @field_validator(
        "business_legal_name",
        "display_name",
        "registration_number",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def tidy_text(cls, value: object) -> object:
        return clean_text(value)

    @field_validator("contact_phone", check_fields=False)
    @classmethod
    def check_contact_phone(cls, value: str | None) -> str | None:
        return None if value is None else normalise_phone(value)

    @field_validator("payout_phone", check_fields=False)
    @classmethod
    def check_payout_phone(cls, value: str | None) -> str | None:
        return None if value is None else normalise_mpesa_phone(value)

    @field_validator("streams", check_fields=False)
    @classmethod
    def no_repeated_streams(cls, value: list[Stream] | None) -> list[Stream] | None:
        return None if value is None else unique_streams(value)

    @model_validator(mode="after")
    def payout_details_together(self):
        fields = self.model_fields_set
        if "payout_phone" in fields or "payout_network" in fields:
            phone = getattr(self, "payout_phone", None)
            network = getattr(self, "payout_network", None)
            if (phone is None) != (network is None):
                raise ValueError("payout_phone and payout_network must be set together")
        return self


class BusinessCreate(_BusinessRules):
    business_legal_name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    business_role: BusinessRole
    business_type: BusinessType
    supplier_kind: SupplierKind | None = None
    location: LocationCreate
    streams: list[Stream] = Field(default_factory=list)
    contact_phone: str | None = None
    contact_email: EmailStr
    registration_number: str | None = Field(default=None, min_length=1, max_length=100)
    payout_phone: str | None = None
    payout_network: PayoutNetwork | None = None

    @model_validator(mode="after")
    def role_rules(self):
        if self.business_type == BusinessType.CONSUMER and (
            self.business_role != BusinessRole.BUYER
        ):
            raise ValueError("only buyers can register as a consumer")
        if self.supplier_kind is not None and (
            self.business_role != BusinessRole.SUPPLIER
        ):
            raise ValueError("supplier_kind is only for suppliers")
        return self


class BusinessUpdate(_BusinessRules):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    location: LocationCreate | None = None
    streams: list[Stream] | None = None
    contact_phone: str | None = None
    contact_email: EmailStr | None = None
    registration_number: str | None = Field(default=None, min_length=1, max_length=100)
    payout_phone: str | None = None
    payout_network: PayoutNetwork | None = None


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_id: uuid.UUID
    business_legal_name: str
    display_name: str | None
    business_role: BusinessRole
    business_type: BusinessType
    supplier_kind: SupplierKind | None
    location: LocationRead
    streams: list[Stream]
    contact_phone: str | None
    contact_email: str
    registration_number: str | None
    approval_status: ApprovalStatus
    approved_at: datetime | None
    rejection_reason: str | None
    payout_phone: str | None
    payout_network: PayoutNetwork | None
    created_at: datetime
    updated_at: datetime


class BusinessPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    business_id: uuid.UUID
    name: str
    business_role: BusinessRole
    business_type: BusinessType
    supplier_kind: SupplierKind | None
    streams: list[Stream]
    location: LocationSummary

    @model_validator(mode="before")
    @classmethod
    def pick_name(cls, data):
        if hasattr(data, "business_legal_name"):
            return {
                "business_id": data.business_id,
                "name": data.display_name or data.business_legal_name,
                "business_role": data.business_role,
                "business_type": data.business_type,
                "supplier_kind": data.supplier_kind,
                "streams": data.streams,
                "location": data.location,
            }
        return data


class DecisionReason(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def tidy_reason(cls, value: object) -> object:
        return clean_text(value)
