import uuid

from models.business import BusinessRole
from schemas.businesses import BusinessPublic, BusinessUpdate
from tests.factories import auth, make_business, make_user


def test_admin_list_with_role_buyer_returns_only_buyers(client, session):
    admin = make_user(session)
    make_business(session, business_role=BusinessRole.BUYER, streams=[])
    make_business(session)

    response = client.get(
        "/admin/businesses", params={"role": "BUYER"}, headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["business_role"] == "BUYER"


def test_admin_get_business_returns_registration_number_and_email(client, session):
    admin = make_user(session)
    business = make_business(session, registration_number="102938475")

    response = client.get(
        f"/admin/businesses/{business.business_id}", headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["registration_number"] == "102938475"
    assert body["contact_email"] == "info@nairobitimber.co.ke"


def test_admin_get_unknown_business_returns_404(client, session):
    admin = make_user(session)

    response = client.get(f"/admin/businesses/{uuid.uuid4()}", headers=auth(admin))

    assert response.status_code == 404


def test_contact_phone_with_foreign_country_code_keeps_that_code():
    data = BusinessUpdate(contact_phone="+250 788 123 456")

    assert data.contact_phone == "+250788123456"


def test_contact_phone_without_plus_sign_gets_one_added():
    data = BusinessUpdate(contact_phone="256712345678")

    assert data.contact_phone == "+256712345678"


def test_public_business_view_accepts_a_plain_dict():
    location_id = uuid.uuid4()
    business_id = uuid.uuid4()

    view = BusinessPublic.model_validate(
        {
            "business_id": business_id,
            "name": "Nairobi Timber",
            "business_role": "SUPPLIER",
            "business_type": "BUSINESS",
            "supplier_kind": None,
            "streams": ["SAWDUST"],
            "location": {
                "location_id": location_id,
                "name": "Westlands",
                "sub_county": "Westlands",
                "county": "Nairobi",
            },
        }
    )

    assert view.name == "Nairobi Timber"
    assert view.location.sub_county == "Westlands"
