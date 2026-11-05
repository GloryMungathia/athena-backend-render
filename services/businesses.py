import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import Business, User
from models.business import ApprovalStatus, BusinessRole
from models.notification import NotificationEvent
from models.user import UserRole
from repositories import businesses as repo
from schemas.businesses import BusinessCreate, BusinessUpdate
from schemas.locations import LocationCreate
from services import locations as location_service
from services.errors import ConflictError, InvalidInputError, NotFoundError

ALLOWED_DECISIONS = {
    "approve": (
        {ApprovalStatus.PENDING, ApprovalStatus.REJECTED},
        ApprovalStatus.APPROVED,
    ),
    "reject": ({ApprovalStatus.PENDING}, ApprovalStatus.REJECTED),
    "suspend": ({ApprovalStatus.APPROVED}, ApprovalStatus.SUSPENDED),
    "restore": ({ApprovalStatus.SUSPENDED}, ApprovalStatus.APPROVED),
}


def _location_id(db: Session, place: LocationCreate) -> uuid.UUID:
    return location_service.save_location(db, place).location_id


def create_business(db: Session, data: BusinessCreate) -> Business:
    values = data.model_dump(exclude={"location"})
    values["location_id"] = _location_id(db, data.location)
    values["streams"] = [stream.value for stream in data.streams]
    values["approval_status"] = ApprovalStatus.PENDING
    return repo.add(db, values)


def get_business(db: Session, business_id: uuid.UUID) -> Business:
    business = repo.get(db, business_id)
    if business is None:
        raise NotFoundError("Business not found.")
    return business


def get_my_business(db: Session, user: User) -> Business:
    if user.business_id is None:
        raise NotFoundError("This account has no business.")
    return get_business(db, user.business_id)


def update_my_business(db: Session, user: User, data: BusinessUpdate) -> Business:
    business = get_my_business(db, user)
    changes = data.model_dump(exclude_unset=True, exclude={"location"})
    if "location" in data.model_fields_set:
        changes["location"] = data.location
    for required in ("contact_email", "location", "streams"):
        if required in changes and changes[required] is None:
            raise InvalidInputError(f"{required} cannot be empty.")
    if "streams" in changes:
        changes["streams"] = [stream.value for stream in data.streams]
    if "payout_phone" in changes and business.business_role == BusinessRole.BUYER:
        if changes["payout_phone"] is not None:
            raise InvalidInputError("Only suppliers and processors receive payouts.")
    if "location" in changes:
        changes["location_id"] = _location_id(db, changes.pop("location"))
    return repo.update(db, business, changes)


def get_visible_business(db: Session, business_id: uuid.UUID, viewer: User) -> Business:
    business = get_business(db, business_id)
    is_owner = viewer.business_id == business.business_id
    is_admin = viewer.user_role == UserRole.ADMIN
    if business.approval_status != ApprovalStatus.APPROVED and not (
        is_owner or is_admin
    ):
        raise NotFoundError("Business not found.")
    return business


def list_businesses(
    db: Session,
    status: ApprovalStatus | None = None,
    role: BusinessRole | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    county: str | None = None,
    sub_county: str | None = None,
) -> tuple[list[Business], int]:
    filters = {
        "status": status,
        "role": role,
        "search": search,
        "county": county,
        "sub_county": sub_county,
    }
    items = repo.list_businesses(db, **filters, limit=limit, offset=offset)
    total = repo.count_businesses(db, **filters)
    return items, total


def decide(
    db: Session,
    admin: User,
    business_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> Business:
    allowed_from, new_status = ALLOWED_DECISIONS[action]
    business = get_business(db, business_id)
    if business.approval_status not in allowed_from:
        raise ConflictError(
            f"Cannot {action} a business that is {business.approval_status.value}."
        )
    repo.notify_owner(db, business, NotificationEvent.APPROVAL_DECISION)
    return repo.update(
        db,
        business,
        {
            "approval_status": new_status,
            "approved_by": admin.user_id,
            "approved_at": datetime.now(timezone.utc),
            "rejection_reason": reason
            if new_status in (ApprovalStatus.REJECTED, ApprovalStatus.SUSPENDED)
            else None,
        },
    )
