import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from core.dependencies import get_user_service, require_admin
from core.exceptions import NotFound
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


def business_name(business: Business) -> str:
    return business.display_name or business.business_legal_name


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
                "name": business_name(business),
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
                "detail": f"{listing.material_or_product} · {business_name(business)}",
                "at": listing.created_at,
            }
            for listing, business in recent_listings
        ],
    }


def listing_row(listing: Listing, business: Business) -> dict:
    return {
        "listing_id": str(listing.listing_id),
        "material_or_product": listing.material_or_product,
        "business_id": str(business.business_id),
        "business_name": business_name(business),
        "stream": listing.stream.value,
        "quantity": float(listing.quantity),
        "unit": listing.unit.value,
        "status": listing.status.value,
        "removed_at": (
            listing.updated_at if listing.status == ListingStatus.CLOSED else None
        ),
    }


@router.get("/listings")
def list_listings(db: Session = Depends(get_db)):
    """Every listing a business has put up, except drafts."""
    rows = db.execute(
        select(Listing, Business)
        .join(Business, Business.business_id == Listing.business_id)
        .where(Listing.status != ListingStatus.DRAFT)
        .order_by(Listing.created_at.desc())
        .limit(500)
    ).all()
    return [listing_row(listing, business) for listing, business in rows]


@router.post("/listings/{listing_id}/remove")
def remove_listing(listing_id: uuid.UUID, db: Session = Depends(get_db)):
    """Staff removal: the listing is closed and no longer visible to businesses."""
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise NotFound()
    listing.status = ListingStatus.CLOSED
    db.commit()
    db.refresh(listing)
    business = db.get(Business, listing.business_id)
    return listing_row(listing, business)


@router.get("/enquiries")
def list_enquiries(db: Session = Depends(get_db)):
    """Status of every enquiry. Messages are not included."""
    buyer = aliased(Business)
    seller = aliased(Business)
    rows = db.execute(
        select(Enquiry, Listing.material_or_product, buyer, seller)
        .join(Listing, Listing.listing_id == Enquiry.listing_id)
        .join(buyer, buyer.business_id == Enquiry.buyer_business_id)
        .join(seller, seller.business_id == Enquiry.seller_business_id)
        .order_by(Enquiry.updated_at.desc())
        .limit(500)
    ).all()
    return [
        {
            "enquiry_id": str(enquiry.enquiry_id),
            "about": material,
            "buyer": business_name(buyer_business),
            "seller": business_name(seller_business),
            "status": enquiry.status.value,
            "updated_at": enquiry.updated_at,
        }
        for enquiry, material, buyer_business, seller_business in rows
    ]