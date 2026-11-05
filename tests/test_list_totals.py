from models.business import ApprovalStatus
from tests.factories import auth, make_business, make_location, make_user


def test_admin_list_total_counts_all_sub_county_matches_not_just_this_page(
    client, session
):
    admin = make_user(session)
    westlands = make_location(session)
    make_business(session, westlands)
    make_business(session, westlands)
    make_business(session, westlands)

    response = client.get(
        "/admin/businesses",
        params={"sub_county": "Westlands", "limit": 1},
        headers=auth(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_admin_list_total_counts_all_businesses_not_just_this_page(client, session):
    admin = make_user(session)
    make_business(session)
    make_business(session, approval_status=ApprovalStatus.APPROVED)
    make_business(session, approval_status=ApprovalStatus.REJECTED)

    response = client.get("/admin/businesses", params={"limit": 1}, headers=auth(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_admin_list_past_last_page_returns_no_items_but_full_total(client, session):
    admin = make_user(session)
    make_business(session)
    make_business(session)

    response = client.get(
        "/admin/businesses", params={"offset": 50}, headers=auth(admin)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"] == []
