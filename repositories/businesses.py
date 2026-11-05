import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from models import Business, Location, Notification
from models.business import ApprovalStatus, BusinessRole
from models.notification import NotificationEvent


def get(db: Session, business_id: uuid.UUID) -> Business | None:
    return db.scalar(
        select(Business)
        .options(selectinload(Business.location), selectinload(Business.user))
        .where(Business.business_id == business_id)
    )


def add(db: Session, values: dict) -> Business:
    business = Business(**values)
    db.add(business)
    db.commit()
    return get(db, business.business_id)


def update(db: Session, business: Business, changes: dict) -> Business:
    for field, value in changes.items():
        setattr(business, field, value)
    db.commit()
    db.refresh(business)
    return get(db, business.business_id)


def notify_owner(db: Session, business: Business, event: NotificationEvent) -> None:
    if business.user is not None:
        db.add(Notification(user_id=business.user.user_id, event_type=event))


def _filtered(
    status: ApprovalStatus | None,
    role: BusinessRole | None,
    search: str | None,
    county: str | None = None,
    sub_county: str | None = None,
):
    query = select(Business)
    if county or sub_county:
        query = query.join(Location, Business.location_id == Location.location_id)
    if county:
        query = query.where(func.lower(Location.county) == county.lower())
    if sub_county:
        query = query.where(func.lower(Location.sub_county) == sub_county.lower())
    if status is not None:
        query = query.where(Business.approval_status == status)
    if role is not None:
        query = query.where(Business.business_role == role)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Business.business_legal_name).like(pattern),
                func.lower(Business.display_name).like(pattern),
                func.lower(Business.contact_email).like(pattern),
            )
        )
    return query


def list_businesses(
    db: Session,
    status: ApprovalStatus | None = None,
    role: BusinessRole | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    county: str | None = None,
    sub_county: str | None = None,
) -> list[Business]:
    query = (
        _filtered(status, role, search, county, sub_county)
        .options(selectinload(Business.location))
        .order_by(Business.created_at.desc(), Business.business_id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(query))


def count_businesses(
    db: Session,
    status: ApprovalStatus | None = None,
    role: BusinessRole | None = None,
    search: str | None = None,
    county: str | None = None,
    sub_county: str | None = None,
) -> int:
    filtered = _filtered(status, role, search, county, sub_county)
    query = select(func.count()).select_from(filtered.subquery())
    return db.scalar(query) or 0
