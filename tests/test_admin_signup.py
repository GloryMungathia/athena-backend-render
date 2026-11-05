import pytest
from pydantic import ValidationError
from sqlalchemy import select

from core.config import Settings, get_settings
from main import app
from models.user import User, UserRole

INVITE = "test-invite-code-123456"
SECRET = "test-secret-that-is-at-least-32-characters-long"


def make_body(**changes):
    body = {
        "full_name": "Wanjiru Kamau",
        "email": "new.admin@huza.co.ke",
        "phone_number": "+254712345678",
        "password": "Strong123",
        "invite_code": INVITE,
    }
    body.update(changes)
    return body


@pytest.fixture
def invite_client(client):
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        jwt_secret=SECRET,
        environment="test",
        admin_invite_code=INVITE,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return client


def find_user(session, email):
    return session.scalar(select(User).where(User.email == email))


def test_creates_an_admin_with_no_business(invite_client, session):
    response = invite_client.post("/auth/register-admin", json=make_body())

    assert response.status_code == 201
    user = find_user(session, "new.admin@huza.co.ke")
    assert user.user_role == UserRole.ADMIN
    assert user.business_id is None
    assert user.first_name == "Wanjiru"
    assert user.last_name == "Kamau"
    assert user.phone == "+254712345678"
    assert user.email_verified_at is not None


def test_email_is_stored_in_lowercase(invite_client, session):
    response = invite_client.post(
        "/auth/register-admin", json=make_body(email="New.Admin@Huza.co.ke")
    )

    assert response.status_code == 201
    assert find_user(session, "new.admin@huza.co.ke") is not None


def test_wrong_invite_code_is_refused(invite_client, session):
    response = invite_client.post(
        "/auth/register-admin", json=make_body(invite_code="not-the-right-code")
    )

    assert response.status_code == 403
    assert find_user(session, "new.admin@huza.co.ke") is None


def test_route_is_off_when_no_invite_code_is_set(client, session):
    response = client.post("/auth/register-admin", json=make_body())

    assert response.status_code == 404
    assert find_user(session, "new.admin@huza.co.ke") is None


def test_same_email_cannot_register_twice(invite_client):
    first = invite_client.post("/auth/register-admin", json=make_body())
    second = invite_client.post("/auth/register-admin", json=make_body())

    assert first.status_code == 201
    assert second.status_code == 409


def test_password_needs_a_number(invite_client):
    response = invite_client.post(
        "/auth/register-admin", json=make_body(password="NoNumbersHere")
    )

    assert response.status_code == 422


def test_full_name_needs_two_names(invite_client):
    response = invite_client.post(
        "/auth/register-admin", json=make_body(full_name="Wanjiru")
    )

    assert response.status_code == 422


def test_invite_code_must_be_long_enough():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="sqlite://",
            jwt_secret=SECRET,
            admin_invite_code="short",
        )


def test_blank_invite_code_means_off():
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        jwt_secret=SECRET,
        admin_invite_code="   ",
    )

    assert settings.admin_invite_code is None