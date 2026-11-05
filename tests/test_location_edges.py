from decimal import Decimal

import pytest
from pydantic import ValidationError

from models.location import OsmType
from repositories import locations as location_repo
from schemas.locations import LocationCreate
from services import locations as service
from services.errors import ConflictError
from services.locations import to_place
from tests.factories import location_payload, make_location


def test_save_location_returns_existing_place_when_saved_at_the_same_moment(
    session, monkeypatch
):
    existing = make_location(session, osm_type=OsmType.NODE, osm_id=777001)
    real_lookup = location_repo.get_by_osm
    calls = []

    def misses_first_time(db, osm_type, osm_id):
        calls.append(osm_id)
        return None if len(calls) == 1 else real_lookup(db, osm_type, osm_id)

    monkeypatch.setattr(location_repo, "get_by_osm", misses_first_time)
    data = LocationCreate(**location_payload(osm_id=777001))

    location = service.save_location(session, data)

    assert location.location_id == existing.location_id
    assert len(calls) == 2


def test_save_location_raises_conflict_when_place_cannot_be_saved_or_found(
    session, monkeypatch
):
    make_location(session, osm_type=OsmType.NODE, osm_id=777002)
    monkeypatch.setattr(location_repo, "get_by_osm", lambda db, osm_type, osm_id: None)
    data = LocationCreate(**location_payload(osm_id=777002))

    with pytest.raises(ConflictError):
        service.save_location(session, data)


def test_location_create_rounds_decimal_coordinates_to_6_places():
    data = LocationCreate(**location_payload(latitude=Decimal("-1.9497123")))

    assert data.latitude == Decimal("-1.949712")


def test_search_result_with_html_in_name_is_skipped():
    item = {
        "osm_type": "node",
        "osm_id": 1,
        "name": "<b>Westlands</b>",
        "display_name": "Westlands, Nairobi, Nairobi County, Kenya",
        "lat": "-1.95",
        "lon": "30.11",
        "address": {"county": "Westlands", "state": "Nairobi County"},
    }

    assert to_place(item) is None


def test_search_result_with_non_numeric_coordinates_is_skipped():
    item = {
        "osm_type": "node",
        "osm_id": 1,
        "name": "Westlands",
        "display_name": "Westlands, Nairobi, Nairobi County, Kenya",
        "lat": "abc",
        "lon": "30.11",
        "address": {"county": "Westlands", "state": "Nairobi County"},
    }

    assert to_place(item) is None


def test_search_result_without_coordinates_is_skipped():
    item = {
        "osm_type": "node",
        "osm_id": 1,
        "name": "Westlands",
        "display_name": "Westlands, Nairobi, Nairobi County, Kenya",
        "lat": None,
        "lon": None,
        "address": {"county": "Westlands", "state": "Nairobi County"},
    }

    assert to_place(item) is None


def test_place_name_that_is_a_number_is_rejected():
    with pytest.raises(ValidationError):
        LocationCreate(**location_payload(name=123))
