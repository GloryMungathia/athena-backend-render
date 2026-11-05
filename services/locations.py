from pydantic import ValidationError
from sqlalchemy.orm import Session

from core import nominatim
from models import Location
from repositories import locations as repo
from schemas.locations import LocationCreate, PlaceResult
from services.errors import ConflictError, ServiceUnavailableError


def save_location(db: Session, data: LocationCreate) -> Location:
    existing = repo.get_by_osm(db, data.osm_type, data.osm_id)
    if existing is not None:
        return existing
    location = repo.add(db, data.model_dump())
    if location is not None:
        return location
    existing = repo.get_by_osm(db, data.osm_type, data.osm_id)
    if existing is None:
        raise ConflictError("This place could not be saved. Try again.")
    return existing


def _first(values: dict, *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


COUNTY_KEYS = ("state", "province", "region")
COUNTY_SUFFIXES = (" county",)
SUB_COUNTY_KEYS = ("county", "state_district", "municipality", "city", "town")
SUB_COUNTY_SUFFIXES = (" sub-county", " sub county", " subcounty", " constituency")


def _without_suffix(value: str | None, suffixes: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    for suffix in suffixes:
        if value.lower().endswith(suffix):
            return value[: -len(suffix)].strip() or None
    return value


def _county(address: dict) -> str | None:
    return _without_suffix(_first(address, *COUNTY_KEYS), COUNTY_SUFFIXES)


def _sub_county(address: dict) -> str | None:
    return _without_suffix(_first(address, *SUB_COUNTY_KEYS), SUB_COUNTY_SUFFIXES)


def to_place(item: dict) -> PlaceResult | None:
    address = item.get("address") or {}
    display_name = _first(item, "display_name")
    county = _county(address)
    sub_county = _sub_county(address)
    if not display_name or not county or not sub_county:
        return None
    try:
        place = LocationCreate.model_validate(
            {
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "name": _first(item, "name") or display_name.split(",")[0],
                "display_name": display_name,
                "latitude": item.get("lat"),
                "longitude": item.get("lon"),
                "sub_county": sub_county,
                "county": county,
            }
        )
    except ValidationError:
        return None
    return PlaceResult(**place.model_dump())


def search_places(query: str, limit: int = 5) -> list[PlaceResult]:
    try:
        results = nominatim.search(query.strip(), limit)
    except nominatim.NominatimError as exc:
        raise ServiceUnavailableError(
            "Place search is not available right now. Try again soon."
        ) from exc
    places = (to_place(item) for item in results)
    return [place for place in places if place is not None]
