from models.enquiry import Enquiry, EnquiryStatus, FailureReason
from models.listing import Unit
from tests.factories import auth, make_business, make_user
from tests.test_admin_listings import make_admin, make_listing


def make_enquiry(session, listing, buyer, seller, **changes):
    values = dict(
        listing_id=listing.listing_id,
        buyer_business_id=buyer.business_id,
        seller_business_id=seller.business_id,
        status=EnquiryStatus.ENQUIRY,
        quantity=10,
        unit=Unit.KILOGRAM,
        unit_price=10,
        total_amount=100,
    )
    values.update(changes)
    enquiry = Enquiry(**values)
    session.add(enquiry)
    session.commit()
    session.refresh(enquiry)
    return enquiry


def test_enquiries_need_an_admin(client, session):
    assert client.get("/admin/enquiries").status_code == 401
    business = make_business(session)
    user = make_user(session, business=business)
    assert client.get("/admin/enquiries", headers=auth(user)).status_code == 403


def test_enquiries_are_empty_when_none_exist(client, session):
    admin = make_admin(session)
    response = client.get("/admin/enquiries", headers=auth(admin))
    assert response.status_code == 200
    assert response.json() == []


def test_lists_enquiries_with_both_business_names(client, session):
    admin = make_admin(session)
    seller = make_business(session)
    buyer = make_business(session)
    listing = make_listing(session, seller, material_or_product="Pine sawdust")
    enquiry = make_enquiry(session, listing, buyer, seller)
    response = client.get("/admin/enquiries", headers=auth(admin))
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["enquiry_id"] == str(enquiry.enquiry_id)
    assert rows[0]["about"] == "Pine sawdust"
    assert rows[0]["buyer"] == (buyer.display_name or buyer.business_legal_name)
    assert rows[0]["seller"] == (seller.display_name or seller.business_legal_name)
    assert rows[0]["status"] == "ENQUIRY"


def test_shows_the_status_of_an_unsuccessful_enquiry(client, session):
    admin = make_admin(session)
    seller = make_business(session)
    buyer = make_business(session)
    listing = make_listing(session, seller)
    make_enquiry(
        session,
        listing,
        buyer,
        seller,
        status=EnquiryStatus.UNSUCCESSFUL,
        failure_reason=FailureReason.PRICE,
    )
    response = client.get("/admin/enquiries", headers=auth(admin))
    assert response.json()[0]["status"] == "UNSUCCESSFUL"