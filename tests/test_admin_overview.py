from models.business import ApprovalStatus
from models.user import UserRole
from tests.factories import auth, make_business, make_user


def make_admin(session):
    return make_user(session, user_role=UserRole.ADMIN)


def test_overview_needs_sign_in(client):
    assert client.get("/admin/overview").status_code == 401


def test_overview_is_refused_for_a_business_user(client, session):
    business = make_business(session)
    user = make_user(session, business=business)
    response = client.get("/admin/overview", headers=auth(user))
    assert response.status_code == 403


def test_overview_is_empty_when_nothing_exists(client, session):
    admin = make_admin(session)
    response = client.get("/admin/overview", headers=auth(admin))
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {
        "waiting_for_approval": 0,
        "approved_businesses": 0,
        "active_listings": 0,
        "open_enquiries": 0,
    }
    assert body["queue"] == []
    assert body["activity"] == []


def test_overview_counts_pending_and_approved_businesses(client, session):
    admin = make_admin(session)
    pending = make_business(session, approval_status=ApprovalStatus.PENDING)
    make_business(session, approval_status=ApprovalStatus.APPROVED)
    make_business(session, approval_status=ApprovalStatus.APPROVED)
    response = client.get("/admin/overview", headers=auth(admin))
    body = response.json()
    assert body["counts"]["waiting_for_approval"] == 1
    assert body["counts"]["approved_businesses"] == 2
    assert [item["business_id"] for item in body["queue"]] == [
        str(pending.business_id)
    ]