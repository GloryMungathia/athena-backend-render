from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Location
from models.location import OsmType


def get_by_osm(db: Session, osm_type: OsmType, osm_id: int) -> Location | None:
    return db.scalar(
        select(Location).where(Location.osm_type == osm_type, Location.osm_id == osm_id)
    )


def add(db: Session, values: dict) -> Location | None:
    try:
        with db.begin_nested():
            location = Location(**values)
            db.add(location)
            db.flush()
    except IntegrityError:
        return None
    db.commit()
    return location
