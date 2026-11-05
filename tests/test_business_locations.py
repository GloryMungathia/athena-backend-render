import pytest

from models import Location
from tests.factories import auth, location_payload, make_business, make_location
from tests.factories import make_user


@pytest.fixture
def owner(session):
    return make_user(session, make_business(session))


@pytest.fixture
def admin(session):
    return make_user(session)


def move(client, owner, **place):
    return client.patch(
        "/businesses/me",
        headers=auth(owner),
        json={"location": location_payload(**place)},
    )


def test_patch_me_with_new_place_saves_it_and_returns_full_location(
    client, session, owner
):
    response = move(client, owner, osm_id=777, name="Sarit Centre")

    assert response.status_code == 200
    location = response.json()["location"]
    assert location["name"] == "Sarit Centre"
    assert location["osm_type"] == "NODE"
    assert location["latitude"] == -1.2675
    assert session.query(Location).filter_by(osm_id=777).count() == 1


def test_patch_me_with_already_saved_place_reuses_it_without_renaming(
    client, session, owner
):
    first = move(client, owner, osm_id=778)
    second = move(client, owner, osm_id=778, name="Westlands again")

    assert second.status_code == 200
    assert (
        second.json()["location"]["location_id"]
        == first.json()["location"]["location_id"]
    )
    assert second.json()["location"]["name"] == "Westlands"
    assert session.query(Location).filter_by(osm_id=778).count() == 1


def test_two_businesses_choosing_same_place_share_one_location(client, session, owner):
    other = make_user(session, make_business(session))

    first = move(client, owner, osm_id=779)
    second = move(client, other, osm_id=779)

    assert (
        first.json()["location"]["location_id"]
        == second.json()["location"]["location_id"]
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"latitude": 200},
        {"longitude": -181},
        {"latitude": "abc"},
        {"longitude": "1e30"},
        {"latitude": None},
        {"osm_id": 0},
        {"osm_type": "area"},
        {"name": "<script>alert(1)</script>"},
        {"name": "   "},
        {"name": "a" * 256},
    ],
    ids=[
        "latitude above 90",
        "longitude below -180",
        "latitude is text",
        "longitude far too large",
        "latitude missing",
        "osm_id is 0",
        "unknown osm_type",
        "name with html",
        "blank name",
        "name over 255 characters",
    ],
)
def test_patch_me_with_invalid_place_field_returns_422(client, owner, bad):
    response = move(client, owner, **bad)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["county", "sub_county"])
def test_patch_me_with_place_missing_county_or_sub_county_returns_422(
    client, owner, field
):
    place = location_payload()
    del place[field]

    response = client.patch(
        "/businesses/me", headers=auth(owner), json={"location": place}
    )

    assert response.status_code == 422


def test_place_that_fails_validation_is_not_saved(client, session, owner):
    move(client, owner, osm_id=781, latitude=200)

    assert session.query(Location).filter_by(osm_id=781).count() == 0


def test_update_that_fails_business_rules_does_not_save_its_place(client, session):
    buyer = make_user(
        session, make_business(session, business_role="BUYER", streams=[])
    )

    response = client.patch(
        "/businesses/me",
        headers=auth(buyer),
        json={
            "location": location_payload(osm_id=782),
            "payout_phone": "0722123456",
            "payout_network": "MPESA",
        },
    )

    assert response.status_code == 422
    assert session.query(Location).filter_by(osm_id=782).count() == 0


def test_get_me_returns_every_location_field(client, owner):
    response = client.get("/businesses/me", headers=auth(owner))

    location = response.json()["location"]
    assert set(location) == {
        "location_id",
        "osm_type",
        "osm_id",
        "name",
        "display_name",
        "latitude",
        "longitude",
        "sub_county",
        "county",
        "created_at",
    }


def test_public_business_view_shows_location_summary_without_coordinates(
    client, session, admin
):
    business = make_business(session, approval_status="APPROVED")

    response = client.get(f"/businesses/{business.business_id}", headers=auth(admin))

    assert set(response.json()["location"]) == {
        "location_id",
        "name",
        "sub_county",
        "county",
    }


def test_admin_list_by_sub_county_ignores_case_and_returns_only_that_sub_county(
    client, session, admin
):
    naivasha = make_location(session, sub_county="Naivasha", county="Nakuru")
    make_business(session, naivasha)
    make_business(session, naivasha)
    make_business(session, make_location(session, sub_county="Nyali", county="Mombasa"))

    response = client.get(
        "/admin/businesses", params={"sub_county": "naivasha"}, headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["location"]["sub_county"] for item in body["items"]} == {"Naivasha"}


def test_admin_list_by_county_ignores_case_and_returns_only_that_county(
    client, session, admin
):
    nakuru = make_location(session, sub_county="Naivasha", county="Nakuru")
    make_business(session, nakuru)
    make_business(session, make_location(session, county="Mombasa"))

    response = client.get(
        "/admin/businesses", params={"county": "nakuru"}, headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["location"]["county"] == "Nakuru"


def test_admin_list_by_sub_county_and_status_applies_both_filters(
    client, session, admin
):
    naivasha = make_location(session, sub_county="Naivasha", county="Nakuru")
    make_business(session, naivasha)
    make_business(session, naivasha, approval_status="APPROVED")

    response = client.get(
        "/admin/businesses",
        params={"sub_county": "Naivasha", "status": "APPROVED"},
        headers=auth(admin),
    )

    assert response.json()["total"] == 1


def test_admin_list_by_sub_county_with_no_businesses_returns_empty_page(client, admin):
    response = client.get(
        "/admin/businesses", params={"sub_county": "Nowhere"}, headers=auth(admin)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


@pytest.mark.parametrize("field", ["county", "sub_county"])
def test_admin_list_with_county_or_sub_county_over_100_characters_returns_422(
    client, admin, field
):
    response = client.get(
        "/admin/businesses", params={field: "a" * 101}, headers=auth(admin)
    )

    assert response.status_code == 422


def test_removed_locations_endpoints_return_404(client):
    assert client.get("/locations").status_code == 404
    assert client.post("/locations", json=location_payload()).status_code == 404
