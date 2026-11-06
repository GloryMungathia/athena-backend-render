from datetime import date, timedelta

import pytest

from models.business import ApprovalStatus
from models.enquiry import EnquiryStatus, FailureReason
from models.listing import ListingStatus, Stream, Unit
from models.payment import Payment, PaymentStatus
from models.price_guide import PriceGuide
from tests.factories import auth, make_business, make_user
from tests.test_admin_enquiries import make_enquiry
from tests.test_admin_listings import make_admin, make_listing


PATHS = [
    "/admin/metrics/exchange-outcomes",
    "/admin/metrics/marketplace-health",
    "/admin/metrics/pilot-learning",
]


def get(client, session, path):
    admin = make_admin(session)
    response = client.get(path, headers=auth(admin))
    assert response.status_code == 200
    return response.json()


def new_enquiry(session, listing, seller, **changes):
    buyer = make_business(session)
    return make_enquiry(session, listing, buyer, seller, **changes)


def published(session, seller, **changes):
    values = dict(
        status=ListingStatus.PUBLISHED,
        stream=Stream.SAWDUST,
        unit=Unit.KILOGRAM,
        unit_price=8,
        photos=["photo.jpg"],
        specifications={"grade": "dry"},
    )
    values.update(changes)
    return make_listing(session, seller, **values)


@pytest.mark.parametrize("path", PATHS)
def test_metrics_need_an_admin(client, session, path):
    assert client.get(path).status_code == 401
    business = make_business(session)
    user = make_user(session, business=business)
    assert client.get(path, headers=auth(user)).status_code == 403


def test_exchange_outcomes_are_empty_without_data(client, session):
    data = get(client, session, PATHS[0])
    assert data["funnel"] == {"opened": 0, "accepted": 0, "paid": 0, "completed": 0}
    assert data["paid_total"] == 0
    assert len(data["paid_by_stream"]) == 4


def test_exchange_outcomes_count_each_stage(client, session):
    seller = make_business(session)
    listing = published(session, seller)
    new_enquiry(session, listing, seller, status=EnquiryStatus.ENQUIRY)
    new_enquiry(session, listing, seller, status=EnquiryStatus.AGREED)
    new_enquiry(session, listing, seller, status=EnquiryStatus.PAID)
    new_enquiry(session, listing, seller, status=EnquiryStatus.COMPLETED)
    data = get(client, session, PATHS[0])
    assert data["funnel"] == {"opened": 4, "accepted": 3, "paid": 2, "completed": 1}


def test_exchange_outcomes_add_up_money_paid(client, session):
    seller = make_business(session)
    listing = published(session, seller)
    enquiry = new_enquiry(session, listing, seller, status=EnquiryStatus.PAID)
    session.add(
        Payment(
            enquiry_id=enquiry.enquiry_id,
            amount=500,
            payer_phone="0700000000",
            reference_id="ref-one",
            status=PaymentStatus.SUCCESSFUL,
        )
    )
    session.commit()
    data = get(client, session, PATHS[0])
    assert data["paid_total"] == 500
    sawdust = next(s for s in data["paid_by_stream"] if s["key"] == "SAWDUST")
    assert sawdust["amount"] == 500


def test_marketplace_health_is_empty_without_data(client, session):
    data = get(client, session, PATHS[1])
    assert data["active_listings"]["total"] == 0
    assert data["completeness"]["published"] == 0
    assert data["completeness"]["rate"] == 0
    assert data["activation"]["rate"] == 0
    assert len(data["first_response"]["weeks"]) == 6
    assert len(data["repeat_use"]["weeks"]) == 5


def test_marketplace_health_counts_listings_and_completeness(client, session):
    seller = make_business(session)
    published(session, seller)
    published(session, seller, photos=[])
    make_listing(session, seller, status=ListingStatus.DRAFT)
    data = get(client, session, PATHS[1])
    assert data["active_listings"]["total"] == 2
    sawdust = next(s for s in data["active_listings"]["streams"] if s["key"] == "SAWDUST")
    assert sawdust["count"] == 2
    assert data["completeness"]["published"] == 2
    assert data["completeness"]["complete"] == 1
    assert data["completeness"]["missing_photo"] == 1
    assert data["completeness"]["rate"] == 50


def test_marketplace_health_reports_first_response_time(client, session):
    seller = make_business(session)
    listing = published(session, seller)
    enquiry = new_enquiry(session, listing, seller)
    enquiry.first_response_at = enquiry.created_at + timedelta(hours=2)
    session.commit()
    data = get(client, session, PATHS[1])
    assert data["first_response"]["median_hours"] == 2


def test_marketplace_health_reports_activation(client, session):
    seller = make_business(session, approval_status=ApprovalStatus.APPROVED)
    make_business(session, approval_status=ApprovalStatus.APPROVED)
    published(session, seller)
    data = get(client, session, PATHS[1])
    assert data["activation"]["approved"] == 2
    assert data["activation"]["activated"] == 1
    assert data["activation"]["rate"] == 50


def test_marketplace_health_reports_price_guidance(client, session):
    seller = make_business(session)
    published(session, seller, material_or_product="Pine sawdust", unit_price=8)
    session.add(
        PriceGuide(
            stream=Stream.SAWDUST,
            material="Pine sawdust",
            unit=Unit.KILOGRAM,
            min_price=5,
            max_price=10,
            source="Market survey",
            source_date=date.today(),
        )
    )
    session.commit()
    data = get(client, session, PATHS[1])
    assert data["price_guidance"]["showing_range_percent"] == 100
    assert data["price_guidance"]["inside_range_percent"] == 100


def test_pilot_learning_is_empty_without_data(client, session):
    data = get(client, session, PATHS[2])
    assert data["failures"] == {"total": 0, "reasons": []}
    assert data["payments"]["total"] == 0
    assert data["seller_response"]["accepted"] == 0


def test_pilot_learning_counts_failure_reasons(client, session):
    seller = make_business(session)
    listing = published(session, seller)
    new_enquiry(
        session,
        listing,
        seller,
        status=EnquiryStatus.UNSUCCESSFUL,
        failure_reason=FailureReason.PRICE,
    )
    new_enquiry(
        session,
        listing,
        seller,
        status=EnquiryStatus.CANCELLED,
        failure_reason=FailureReason.DECLINED,
    )
    data = get(client, session, PATHS[2])
    assert data["failures"]["total"] == 2
    keys = {reason["key"] for reason in data["failures"]["reasons"]}
    assert keys == {"PRICE", "DECLINED"}
    assert data["seller_response"]["declined"] == 1


def test_pilot_learning_reports_payments(client, session):
    seller = make_business(session)
    listing = published(session, seller)
    enquiry = new_enquiry(session, listing, seller, status=EnquiryStatus.PAID)
    session.add(
        Payment(
            enquiry_id=enquiry.enquiry_id,
            amount=300,
            payer_phone="0700000000",
            reference_id="ref-two",
            status=PaymentStatus.SUCCESSFUL,
        )
    )
    session.commit()
    data = get(client, session, PATHS[2])
    assert data["payments"]["total"] == 1
    assert data["payments"]["confirmed"] == 1
    assert data["payments"]["success_rate"] == 100
    assert data["seller_response"]["accepted"] == 1