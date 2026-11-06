from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.business import ApprovalStatus, Business
from models.enquiry import Enquiry, EnquiryStatus, FailureReason
from models.listing import Listing, ListingStatus, Stream
from models.payment import Payment, PaymentStatus
from models.price_guide import PriceGuide
from models.user import User, UserRole


router = APIRouter(prefix="/metrics")

STREAM_LABELS = {
    Stream.SAWDUST: "Sawdust",
    Stream.PLASTIC: "Plastic",
    Stream.GARMENT_OFFCUTS: "Garment offcuts",
    Stream.GLASS: "Glass",
}

REASON_LABELS = {
    FailureReason.NO_PARTNER_FOUND: "No partner found",
    FailureReason.QUALITY: "Quality mismatch",
    FailureReason.PRICE: "Price",
    FailureReason.TRANSPORT: "Transport",
    FailureReason.QUANTITY: "Quantity",
    FailureReason.TRUST: "Trust",
    FailureReason.PAYMENT: "Payment problem",
    FailureReason.DECLINED: "Declined",
    FailureReason.OTHER: "Other",
}

ACCEPTED_STATUSES = (
    EnquiryStatus.AGREED,
    EnquiryStatus.PAID,
    EnquiryStatus.COMPLETED,
)
PAID_STATUSES = (EnquiryStatus.PAID, EnquiryStatus.COMPLETED)
FAILED_STATUSES = (EnquiryStatus.CANCELLED, EnquiryStatus.UNSUCCESSFUL)
WEEK = timedelta(weeks=1)
ACTIVATION_TARGET = 70


def percent(part, whole):
    return round(part * 100 / whole) if whole else 0


def median_or_zero(values, digits=1):
    return round(median(values), digits) if values else 0


def pilot_user_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(User).where(User.user_role != UserRole.ADMIN)
        )
        or 0
    )


def enquiries_since(db: Session, since, stream):
    query = (
        select(Enquiry)
        .join(Listing, Listing.listing_id == Enquiry.listing_id)
        .where(Enquiry.created_at >= since)
    )
    if stream is not None:
        query = query.where(Listing.stream == stream)
    return list(db.scalars(query))


def payments_since(db: Session, since, stream):
    query = (
        select(Payment, Listing.stream)
        .join(Enquiry, Enquiry.enquiry_id == Payment.enquiry_id)
        .join(Listing, Listing.listing_id == Enquiry.listing_id)
        .where(Payment.created_at >= since)
    )
    if stream is not None:
        query = query.where(Listing.stream == stream)
    return db.execute(query).all()


def published_listings(db: Session, stream):
    query = select(Listing).where(Listing.status == ListingStatus.PUBLISHED)
    if stream is not None:
        query = query.where(Listing.stream == stream)
    return list(db.scalars(query))


def was_accepted(enquiry: Enquiry) -> bool:
    return enquiry.accepted_at is not None or enquiry.status in ACCEPTED_STATUSES


def response_hours(enquiry: Enquiry) -> float:
    return (enquiry.first_response_at - enquiry.created_at).total_seconds() / 3600


def guide_index(db: Session):
    index = defaultdict(list)
    for guide in db.scalars(select(PriceGuide)):
        key = (guide.stream, guide.material.strip().lower(), guide.unit)
        index[key].append(guide)
    return index


def guide_position(listing: Listing, index):
    key = (listing.stream, listing.material_or_product.strip().lower(), listing.unit)
    guides = index.get(key)
    if not guides:
        return None
    price = listing.unit_price
    if any(guide.min_price <= price <= guide.max_price for guide in guides):
        return "inside"
    if price > max(guide.max_price for guide in guides):
        return "above"
    return "below"


def price_positions(listings, index):
    return Counter(
        position
        for position in (guide_position(listing, index) for listing in listings)
        if position is not None
    )


def first_activity(db: Session):
    firsts = {}
    listing_rows = db.execute(
        select(Listing.business_id, func.min(Listing.created_at))
        .where(Listing.status != ListingStatus.DRAFT)
        .group_by(Listing.business_id)
    ).all()
    enquiry_rows = db.execute(
        select(Enquiry.buyer_business_id, func.min(Enquiry.created_at)).group_by(
            Enquiry.buyer_business_id
        )
    ).all()
    for business_id, moment in [*listing_rows, *enquiry_rows]:
        if business_id not in firsts or moment < firsts[business_id]:
            firsts[business_id] = moment
    return firsts


def buyer_history(db: Session):
    history = defaultdict(list)
    rows = db.execute(
        select(Enquiry.buyer_business_id, Enquiry.created_at).order_by(
            Enquiry.created_at
        )
    ).all()
    for business_id, moment in rows:
        history[business_id].append(moment)
    return history


def repeat_rate(history, current, weeks):
    window = timedelta(weeks=weeks)
    eligible = [times for times in history.values() if current - times[0] >= window]
    returned = [
        times for times in eligible if len(times) > 1 and times[1] - times[0] <= window
    ]
    return percent(len(returned), len(eligible))


@router.get("/exchange-outcomes")
def exchange_outcomes(
    days: int = Query(30, ge=1, le=365),
    stream: Stream | None = None,
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    enquiries = enquiries_since(db, since, stream)
    payments = payments_since(db, since, stream)
    paid_ids = {
        payment.enquiry_id
        for payment, _ in payments
        if payment.status == PaymentStatus.SUCCESSFUL
    }
    paid_amount = defaultdict(float)
    for payment, payment_stream in payments:
        if payment.status == PaymentStatus.SUCCESSFUL:
            paid_amount[payment_stream] += float(payment.amount)

    return {
        "days": days,
        "pilot_users": pilot_user_count(db),
        "funnel": {
            "opened": len(enquiries),
            "accepted": sum(1 for e in enquiries if was_accepted(e)),
            "paid": sum(
                1
                for e in enquiries
                if e.status in PAID_STATUSES or e.enquiry_id in paid_ids
            ),
            "completed": sum(
                1 for e in enquiries if e.status == EnquiryStatus.COMPLETED
            ),
        },
        "paid_total": round(sum(paid_amount.values()), 2),
        "paid_by_stream": [
            {
                "key": item.value,
                "label": STREAM_LABELS[item],
                "amount": round(paid_amount[item], 2),
            }
            for item in Stream
        ],
    }


@router.get("/marketplace-health")
def marketplace_health(
    days: int = Query(30, ge=1, le=365),
    stream: Stream | None = None,
    db: Session = Depends(get_db),
):
    current = datetime.now(timezone.utc)
    since = current - timedelta(days=days)

    published = published_listings(db, stream)
    active = [listing for listing in published if listing.updated_at >= since]
    active_by_stream = Counter(listing.stream for listing in active)

    missing_photo = sum(1 for listing in published if not listing.photos)
    missing_fields = sum(
        1 for listing in published if listing.photos and not listing.specifications
    )
    complete = len(published) - missing_photo - missing_fields

    enquiries = enquiries_since(db, current - timedelta(days=max(days, 42)), stream)
    responded = [
        response_hours(e)
        for e in enquiries
        if e.created_at >= since and e.first_response_at is not None
    ]
    older = [e for e in enquiries if current - e.created_at >= timedelta(days=14)]
    response_weeks = []
    for i in range(6):
        start = current - WEEK * (6 - i)
        end = start + WEEK
        values = [
            response_hours(e)
            for e in enquiries
            if e.first_response_at is not None and start <= e.created_at < end
        ]
        response_weeks.append({"label": f"W{i + 1}", "value": median_or_zero(values)})

    approved_ids = set(
        db.scalars(
            select(Business.business_id).where(
                Business.approval_status == ApprovalStatus.APPROVED
            )
        )
    )
    firsts = {
        business_id: moment
        for business_id, moment in first_activity(db).items()
        if business_id in approved_ids
    }
    activation_weeks = []
    for i in range(6):
        end = current - WEEK * (5 - i)
        reached = sum(1 for moment in firsts.values() if moment <= end)
        activation_weeks.append(
            {"label": f"W{i + 1}", "value": percent(reached, len(approved_ids))}
        )

    history = buyer_history(db)
    repeat_weeks = [
        {"label": f"Wk {weeks}", "value": repeat_rate(history, current, weeks)}
        for weeks in (2, 4, 6, 8, 10)
    ]

    positions = price_positions(published, guide_index(db))
    shown = sum(positions.values())

    return {
        "days": days,
        "pilot_users": pilot_user_count(db),
        "active_listings": {
            "total": len(active),
            "streams": [
                {
                    "key": item.value,
                    "label": STREAM_LABELS[item],
                    "count": active_by_stream[item],
                }
                for item in Stream
            ],
        },
        "first_response": {
            "median_hours": median_or_zero(responded),
            "no_response_percent": percent(
                sum(1 for e in older if e.first_response_at is None), len(older)
            ),
            "weeks": response_weeks,
        },
        "activation": {
            "rate": percent(len(firsts), len(approved_ids)),
            "activated": len(firsts),
            "approved": len(approved_ids),
            "target": ACTIVATION_TARGET,
            "weeks": activation_weeks,
        },
        "completeness": {
            "rate": percent(complete, len(published)),
            "published": len(published),
            "complete": complete,
            "missing_photo": missing_photo,
            "missing_fields": missing_fields,
        },
        "repeat_use": {
            "rate": percent(
                sum(1 for times in history.values() if len(times) > 1), len(history)
            ),
            "weeks": repeat_weeks,
        },
        "price_guidance": {
            "rate": percent(shown, len(published)),
            "showing_range_percent": percent(shown, len(published)),
            "inside_range_percent": percent(positions["inside"], shown),
        },
    }


@router.get("/pilot-learning")
def pilot_learning(
    days: int = Query(30, ge=1, le=365),
    stream: Stream | None = None,
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    enquiries = enquiries_since(db, since, stream)
    payments = [payment for payment, _ in payments_since(db, since, stream)]

    failed = [e for e in enquiries if e.status in FAILED_STATUSES]
    reason_counts = Counter(e.failure_reason for e in failed)

    confirmed = [p for p in payments if p.status == PaymentStatus.SUCCESSFUL]
    declined_payments = sum(1 for p in payments if p.status == PaymentStatus.FAILED)
    seconds = [
        (p.paid_at - p.created_at).total_seconds() for p in confirmed if p.paid_at
    ]

    accepted = sum(1 for e in enquiries if was_accepted(e))
    declined = sum(
        1
        for e in enquiries
        if e.failure_reason == FailureReason.DECLINED and not was_accepted(e)
    )
    answered_fast = sum(
        1
        for e in enquiries
        if e.first_response_at is not None and response_hours(e) <= 24
    )
    no_answer = sum(
        1
        for e in enquiries
        if e.first_response_at is None
        and not was_accepted(e)
        and e.failure_reason != FailureReason.DECLINED
    )

    positions = price_positions(published_listings(db, stream), guide_index(db))
    shown = sum(positions.values())

    return {
        "days": days,
        "pilot_users": pilot_user_count(db),
        "failures": {
            "total": len(failed),
            "reasons": [
                {"key": reason.value, "label": REASON_LABELS[reason], "count": count}
                for reason, count in reason_counts.most_common()
                if reason is not None
            ],
        },
        "payments": {
            "success_rate": percent(len(confirmed), len(payments)),
            "median_seconds": round(median(seconds)) if seconds else 0,
            "total": len(payments),
            "confirmed": len(confirmed),
            "not_confirmed": len(payments) - len(confirmed) - declined_payments,
            "declined": declined_payments,
        },
        "seller_response": {
            "rate": percent(answered_fast, len(enquiries)),
            "accepted": accepted,
            "declined": declined,
            "no_answer": no_answer,
        },
        "price_guide": {
            "inside_percent": percent(positions["inside"], shown),
            "above_percent": percent(positions["above"], shown),
            "below_percent": percent(positions["below"], shown),
        },
    }