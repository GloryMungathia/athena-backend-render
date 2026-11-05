import uuid

import pytest

from models import Location, Notification
from models.business import ApprovalStatus, BusinessRole, BusinessType
from schemas.businesses import BusinessCreate
from schemas.locations import LocationCreate
from services import businesses as service
from tests.factories import auth, location_payload, make_business, make_user


@pytest.fixture
def owner(session):
    business = make_business(session)
    return make_user(session, business)


@pytest.fixture
def admin(session):
    return make_user(session)


def new_business(**place):
    return BusinessCreate(
        business_legal_name="Jiko Fuel Traders",
        business_role=BusinessRole.BUYER,
        business_type=BusinessType.BUSINESS,
        location=LocationCreate(**location_payload(**place)),
        contact_email="hello@jikofuel.co.ke",
    )


def test_create_business_starts_as_pending_with_no_streams(session):
    business = service.create_business(session, new_business())

    assert business.approval_status == ApprovalStatus.PENDING
    assert business.streams == []


def test_create_business_saves_the_chosen_place_as_its_location(session):
    business = service.create_business(session, new_business(osm_id=880001))

    assert business.location.osm_id == 880001
    assert business.location.sub_county == "Westlands"


def test_create_business_reuses_already_saved_place_without_duplicating(session):
    first = service.create_business(session, new_business(osm_id=880002))
    second = service.create_business(session, new_business(osm_id=880002))

    assert second.location_id == first.location_id
    assert session.query(Location).filter_by(osm_id=880002).count() == 1


def test_get_me_without_token_returns_401(client, owner):
    response = client.get("/businesses/me")

    assert response.status_code == 401


def test_get_me_returns_owners_full_business_with_location(client, owner):
    response = client.get("/businesses/me", headers=auth(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["contact_email"] == "info@nairobitimber.co.ke"
    assert body["location"]["sub_county"] == "Westlands"
    assert body["approval_status"] == "PENDING"


def test_get_me_as_admin_returns_404_because_admins_have_no_business(client, admin):
    response = client.get("/businesses/me", headers=auth(admin))

    assert response.status_code == 404


def test_patch_me_updates_name_phone_payout_and_streams(client, owner):
    response = client.patch(
        "/businesses/me",
        headers=auth(owner),
        json={
            "display_name": "Nairobi Timber",
            "contact_phone": "0712 000 111",
            "payout_phone": "0722123456",
            "payout_network": "MPESA",
            "streams": ["SAWDUST", "GLASS"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Nairobi Timber"
    assert body["contact_phone"] == "+254712000111"
    assert body["payout_phone"] == "+254722123456"
    assert body["streams"] == ["SAWDUST", "GLASS"]


def test_patch_me_ignores_role_and_approval_status(client, owner):
    response = client.patch(
        "/businesses/me",
        headers=auth(owner),
        json={"business_role": "BUYER", "approval_status": "APPROVED"},
    )

    assert response.status_code == 200
    assert response.json()["business_role"] == "SUPPLIER"
    assert response.json()["approval_status"] == "PENDING"


def test_patch_me_with_null_location_returns_422(client, owner):
    response = client.patch(
        "/businesses/me", headers=auth(owner), json={"location": None}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "location cannot be empty."


def test_patch_me_with_null_email_returns_422(client, owner):
    response = client.patch(
        "/businesses/me", headers=auth(owner), json={"contact_email": None}
    )

    assert response.status_code == 422


def test_patch_me_as_buyer_with_payout_phone_returns_422(client, session):
    buyer = make_user(
        session, make_business(session, business_role=BusinessRole.BUYER, streams=[])
    )

    response = client.patch(
        "/businesses/me",
        headers=auth(buyer),
        json={"payout_phone": "0722123456", "payout_network": "MPESA"},
    )

    assert response.status_code == 422


def test_public_business_view_hides_email_phone_and_payout(client, session, owner):
    approved = make_business(
        session,
        approval_status=ApprovalStatus.APPROVED,
        display_name="Mazingira Boards",
        contact_email="secret@mazingira.co.ke",
    )

    response = client.get(f"/businesses/{approved.business_id}", headers=auth(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Mazingira Boards"
    assert "contact_email" not in body
    assert "contact_phone" not in body
    assert "payout_phone" not in body


def test_public_business_view_of_pending_business_returns_404_to_others(
    client, session, owner
):
    pending = make_business(session)

    response = client.get(f"/businesses/{pending.business_id}", headers=auth(owner))

    assert response.status_code == 404


def test_public_business_view_of_unknown_business_returns_404(client, owner):
    response = client.get(f"/businesses/{uuid.uuid4()}", headers=auth(owner))

    assert response.status_code == 404
    assert response.json()["detail"] == "Business not found."


def test_public_business_view_of_own_pending_business_returns_200(
    client, session, owner
):
    response = client.get(f"/businesses/{owner.business_id}", headers=auth(owner))

    assert response.status_code == 200


def test_admin_endpoints_return_403_for_business_users(client, owner):
    assert client.get("/admin/businesses", headers=auth(owner)).status_code == 403
    response = client.post(
        f"/admin/businesses/{owner.business_id}/approve", headers=auth(owner)
    )
    assert response.status_code == 403


def test_admin_list_by_status_returns_only_that_status(client, session, admin):
    make_business(session, business_legal_name="Pending One")
    make_business(
        session,
        business_legal_name="Approved One",
        approval_status=ApprovalStatus.APPROVED,
    )

    response = client.get(
        "/admin/businesses", headers=auth(admin), params={"status": "PENDING"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["business_legal_name"] == "Pending One"


def test_admin_list_search_matches_legal_name_ignoring_case(client, session, admin):
    make_business(session, business_legal_name="Thika EcoFibre")
    make_business(session, business_legal_name="Kisumu Textile Reuse")

    response = client.get(
        "/admin/businesses", headers=auth(admin), params={"search": "ecofibre"}
    )

    assert response.json()["total"] == 1


def test_admin_approve_sets_approved_and_notifies_owner(client, session, admin, owner):
    response = client.post(
        f"/admin/businesses/{owner.business_id}/approve", headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "APPROVED"
    assert body["approved_at"] is not None
    notification = session.query(Notification).filter_by(user_id=owner.user_id).one()
    assert notification.event_type.value == "APPROVAL_DECISION"


def test_admin_reject_requires_reason_and_saves_it(client, admin, owner):
    path = f"/admin/businesses/{owner.business_id}/reject"

    assert client.post(path, headers=auth(admin), json={}).status_code == 422
    response = client.post(
        path, headers=auth(admin), json={"reason": "Registration number is missing"}
    )
    assert response.status_code == 200
    assert response.json()["approval_status"] == "REJECTED"
    assert response.json()["rejection_reason"] == "Registration number is missing"


def test_admin_suspend_then_restore_returns_business_to_approved(
    client, session, admin
):
    business = make_business(session, approval_status=ApprovalStatus.APPROVED)
    base = f"/admin/businesses/{business.business_id}"

    suspended = client.post(
        f"{base}/suspend",
        headers=auth(admin),
        json={"reason": "Reported for fake listings"},
    )
    restored = client.post(f"{base}/restore", headers=auth(admin))

    assert suspended.json()["approval_status"] == "SUSPENDED"
    assert restored.json()["approval_status"] == "APPROVED"
    assert restored.json()["rejection_reason"] is None


def test_admin_suspend_of_pending_business_returns_409(client, admin, owner):
    response = client.post(
        f"/admin/businesses/{owner.business_id}/suspend",
        headers=auth(admin),
        json={"reason": "Reported for fake listings"},
    )

    assert response.status_code == 409


def test_admin_approve_unknown_business_returns_404(client, admin):
    response = client.post(
        f"/admin/businesses/{uuid.uuid4()}/approve", headers=auth(admin)
    )

    assert response.status_code == 404
