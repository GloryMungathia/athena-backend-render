import pytest

from tests.factories import auth, make_business, make_user

PROTECTED = [
    ("get", "/businesses/me"),
    ("patch", "/businesses/me"),
    ("get", "/businesses/places?q=Westlands"),
    ("get", "/admin/businesses"),
]


@pytest.fixture
def owner(session):
    return make_user(session, make_business(session))


@pytest.mark.parametrize("method,path", PROTECTED)
def test_business_endpoints_without_token_return_401(client, method, path):
    response = client.request(method, path, json={})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated."


@pytest.mark.parametrize("method,path", PROTECTED)
def test_business_endpoints_with_invalid_token_return_401(client, method, path):
    response = client.request(
        method, path, json={}, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


def test_old_user_id_header_no_longer_signs_in(client, owner):
    response = client.get("/businesses/me", headers={"X-User-Id": str(owner.user_id)})

    assert response.status_code == 401


def test_token_stops_working_after_the_user_signs_out_everywhere(
    client, session, owner
):
    headers = auth(owner)
    owner.token_version += 1
    session.flush()

    response = client.get("/businesses/me", headers=headers)

    assert response.status_code == 401


def test_token_for_a_deleted_user_returns_401(client, session):
    business = make_business(session)
    user = make_user(session, business)
    headers = auth(user)
    session.delete(user)
    session.flush()

    response = client.get("/businesses/me", headers=headers)

    assert response.status_code == 401


def test_business_user_token_on_admin_list_returns_403_with_message(client, owner):
    response = client.get("/admin/businesses", headers=auth(owner))

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have permission to do this."


def test_owner_token_opens_their_own_business(client, owner):
    response = client.get("/businesses/me", headers=auth(owner))

    assert response.status_code == 200
    assert response.json()["business_id"] == str(owner.business_id)
