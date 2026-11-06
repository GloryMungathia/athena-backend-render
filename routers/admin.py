import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.dependencies import get_user_service, require_admin
from database import get_db
from models.business import ApprovalStatus, Business
from models.enquiry import Enquiry, EnquiryStatus
from models.listing import Listing, ListingStatus
from models.user import User, UserRole
from schemas.auth import UserOut, UserPage
from services.user_service import UserService


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/users", response_model=UserPage)
def list_users(
    role: UserRole | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: UserService = Depends(get_user_service),
):
    items, total = service.list_users(role=role, limit=limit, offset=offset)
    return UserPage(
        items=[UserOut.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Clear a lockout caused by too many failed sign-ins."""
    return UserOut.model_validate(service.unlock(user_id))


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Counts, approval queue and recent activity for the staff dashboard."""

    def count(model, *conditions) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    pending = Business.approval_status == ApprovalStatus.PENDING
    waiting = count(Business, pending)
    approved = count(Business, Business.approval_status == ApprovalStatus.APPROVED)
    active_listings = count(Listing, Listing.status == ListingStatus.PUBLISHED)
    open_enquiries = count(
        Enquiry,
        Enquiry.status.in_(
            [EnquiryStatus.ENQUIRY, EnquiryStatus.AGREED, EnquiryStatus.PAID]
        ),
    )
    pilot_users = count(User, User.user_role != UserRole.ADMIN)

    queue = db.execute(
        select(Business).where(pending).order_by(Business.created_at).limit(5)
    ).scalars()
    recent_listings = db.execute(
        select(Listing, Business)
        .join(Business, Business.business_id == Listing.business_id)
        .order_by(Listing.created_at.desc())
        .limit(5)
    ).all()

    return {
        "pilot_users": pilot_users,
        "counts": {
            "waiting_for_approval": waiting,
            "approved_businesses": approved,
            "active_listings": active_listings,
            "open_enquiries": open_enquiries,
        },
        "queue": [
            {
                "business_id": str(business.business_id),
                "name": business.display_name or business.business_legal_name,
                "kind": (business.supplier_kind or business.business_role).value,
                "place": business.location.sub_county if business.location else "",
                "submitted_at": business.created_at,
            }
            for business in queue
        ],
        "activity": [
            {
                "id": str(listing.listing_id),
                "kind": "NEW_LISTING",
                "title": "New listing",
                "detail": (
                    f"{listing.material_or_product} · "
                    f"{business.display_name or business.business_legal_name}"
                ),
                "at": listing.created_at,
            }
            for listing, business in recent_listings
        ],
    }
