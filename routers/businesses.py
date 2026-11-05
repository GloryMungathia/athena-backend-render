import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.dependencies import get_current_user, require_admin
from database import get_db
from models import User
from models.business import ApprovalStatus, BusinessRole
from schemas.businesses import (
    BusinessPublic,
    BusinessRead,
    BusinessUpdate,
    DecisionReason,
)
from schemas.common import Page
from schemas.locations import PlaceResult
from services import businesses as service
from services import locations as location_service

router = APIRouter(prefix="/businesses", tags=["Businesses"])
admin_router = APIRouter(
    prefix="/admin/businesses",
    tags=["Admin: Businesses"],
    dependencies=[Depends(require_admin)],
)


@router.get("/places", response_model=list[PlaceResult])
def search_places(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
    user: User = Depends(get_current_user),
):
    return location_service.search_places(q, limit)


@router.get("/me", response_model=BusinessRead)
def get_my_business(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return service.get_my_business(db, user)


@router.patch("/me", response_model=BusinessRead)
def update_my_business(
    data: BusinessUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return service.update_my_business(db, user, data)


@router.get("/{business_id}", response_model=BusinessPublic)
def get_business(
    business_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return service.get_visible_business(db, business_id, user)


@admin_router.get("", response_model=Page[BusinessRead])
def list_businesses(
    db: Session = Depends(get_db),
    status: ApprovalStatus | None = None,
    role: BusinessRole | None = None,
    search: str | None = Query(None, max_length=100),
    county: str | None = Query(None, max_length=100),
    sub_county: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    items, total = service.list_businesses(
        db, status, role, search, limit, offset, county, sub_county
    )
    return Page[BusinessRead](items=items, total=total, limit=limit, offset=offset)


@admin_router.get("/{business_id}", response_model=BusinessRead)
def get_business_for_review(business_id: uuid.UUID, db: Session = Depends(get_db)):
    return service.get_business(db, business_id)


@admin_router.post("/{business_id}/approve", response_model=BusinessRead)
def approve_business(
    business_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return service.decide(db, admin, business_id, "approve")


@admin_router.post("/{business_id}/reject", response_model=BusinessRead)
def reject_business(
    business_id: uuid.UUID,
    data: DecisionReason,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return service.decide(db, admin, business_id, "reject", data.reason)


@admin_router.post("/{business_id}/suspend", response_model=BusinessRead)
def suspend_business(
    business_id: uuid.UUID,
    data: DecisionReason,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return service.decide(db, admin, business_id, "suspend", data.reason)


@admin_router.post("/{business_id}/restore", response_model=BusinessRead)
def restore_business(
    business_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return service.decide(db, admin, business_id, "restore")
