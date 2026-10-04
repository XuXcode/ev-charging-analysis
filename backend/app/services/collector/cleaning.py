"""Conservative identity cleaning, not a spatial-analysis algorithm."""

import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from app.schemas.data import StationCreate


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).casefold()


def identity_hash(name, longitude, latitude):
    # GCJ-02, 6 decimal places. No fuzzy name matching or distance-based merge.
    position = [Decimal(str(v)).quantize(Decimal("0.000001")) for v in (longitude, latitude)]
    identity = f"amap|{normalize_name(name)}|{position[0]}|{position[1]}"
    return hashlib.sha256(identity.encode()).hexdigest()


def clean_poi(poi, scope, city_name, source_id, collected_at):
    if not isinstance(poi, dict):
        return None, "invalid_record"
    name, poi_id = poi.get("name"), poi.get("id")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(poi_id, str)
        or not poi_id.strip()
    ):
        return None, "missing_identity"
    adcode = str(poi.get("adcode", ""))
    if adcode != scope["adcode"] or adcode[:4] != scope["cityCode"][:4]:
        return None, "outside_requested_district"
    station_type = poi.get("type") if isinstance(poi.get("type"), str) else ""
    if "充电站" not in name + station_type or any(
        word in name + station_type for word in ("自行车", "电瓶车", "两轮", "换电站")
    ):
        return None, "not_ev_charging_station"
    try:
        parts = poi["location"].split(",")
        if len(parts) != 2:
            raise ValueError
        lng, lat = (Decimal(value) for value in parts)
        if not lng.is_finite() or not lat.is_finite() or lng == 0 or lat == 0:
            raise ValueError
        # A deliberately broad plausibility box, not a province-boundary containment test.
        if not (Decimal("108") < lng < Decimal("115") and Decimal("24") < lat < Decimal("31")):
            return None, "implausible_hunan_coordinates"
        payload = StationCreate(
            poi_id=poi_id.strip(),
            name=unicodedata.normalize("NFKC", name).strip(),
            address=poi.get("address") if isinstance(poi.get("address"), str) else None,
            province="湖南省",
            city=city_name,
            district=scope["name"],
            adcode=adcode,
            longitude=float(lng),
            latitude=float(lat),
            station_type="新能源汽车充电站",
            source="amap",
            collected_at=collected_at,
            data_source_id=source_id,
            public_charger_count=None,
        )
    except (KeyError, AttributeError, TypeError, ValueError, InvalidOperation, ValidationError):
        return None, "invalid_fields_or_coordinates"
    return payload, None
