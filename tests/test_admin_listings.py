import uuid

from models.listing import Listing, ListingStatus, ListingType, Stream, Unit
from models.user import UserRole
from tests.factories import auth, make_business, make_user


def make_admin(session):
    return make_user(session, user_role=UserRole.ADMIN)


def make_listing(session, business, **changes):
    values = dict(
        business_id=business.business_id,
        listing_type=ListingType.RAW_BYPRODUCT,
        stream=Stream.SAWDUST,
        material_or_product="Pine sawdust",
        quantity=100,
        unit=Unit.KILOGRAM,
        location_id=business.location_id,
        unit_price=10,
        status=ListingStatus.PUBLISHED,
    )
    values.update(changes)
    listing = Listing(**values)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def test_listings_need_an_admin(client, session):
    assert client.get("/admin/listings").status_code == 401
    business = make_business(session)
    user = make_user(session, business=business)
    assert client.get("/admin/listings", headers=auth(user)).status_code == 403


def test_lists_listings_with_the_business_name_and_skips_drafts(client, session):
    admin = make_admin(session)
    business = make_business(session)
    live = make_listing(session, business)
    make_listing(session, business, status=ListingStatus.DRAFT)
    response = client.get("/admin/listings", headers=auth(admin))
    assert response.status_code == 200
    rows = response.json()
    assert [row["listing_id"] for row in rows] == [str(live.listing_id)]
    assert rows[0]["business_name"] == (
        business.display_name or business.business_legal_name
    )
    assert rows[0]["status"] == "PUBLISHED"
    assert rows[0]["removed_at"] is None


def test_removing_a_listing_closes_it(client, session):
    admin = make_admin(session)
    business = make_business(session)
    listing = make_listing(session, business)
    response = client.post(
        f"/admin/listings/{listing.listing_id}/remove", headers=auth(admin)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLOSED"
    assert body["removed_at"] is not None


def test_removing_an_unknown_listing_is_not_found(client, session):
    admin = make_admin(session)
    response = client.post(
        f"/admin/listings/{uuid.uuid4()}/remove", headers=auth(admin)
    )
    assert response.status_code == 404