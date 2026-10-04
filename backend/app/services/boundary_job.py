"""Version real city/county boundaries independently of the POI collector."""

import hashlib
import json
import time
from pathlib import Path
from urllib.request import urlopen

from shapely.geometry import shape
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisBoundary, AnalysisScopeQuality
from app.models.entities import utc_now
from app.services.collector.client import DISTRICT_URL, AMapClient

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "backend/.runtime/boundaries"


def digest(data):
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fetch_city(code):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{code}_full.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = f"https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json"
    for attempt in range(3):
        try:
            with urlopen(url, timeout=20) as response:
                data = json.load(response)
            if data.get("type") != "FeatureCollection" or not data.get("features"):
                raise ValueError("行政区来源未返回有效FeatureCollection")
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))


def import_boundaries(session):
    scopes = {row.adcode: row for row in session.scalars(select(AnalysisScopeQuality))}
    if len(scopes) != 122:
        raise ValueError("需先执行治理任务，确认122区县采集范围")
    province = json.loads((ROOT / "src/assets/hunan.geojson.json").read_text(encoding="utf-8"))
    prepared = []
    found = set()
    for city in province["features"]:
        code = str(city["properties"]["adcode"])
        prepared.append(
            (city, code, "city", "https://geo.datav.aliyun.com/areas_v3/bound/430000_full.json")
        )
        for county in fetch_city(code)["features"]:
            county_code = str(county["properties"]["adcode"])
            if county_code in scopes:
                if county_code in found:
                    raise ValueError("边界来源存在重复区县编码")
                found.add(county_code)
                prepared.append(
                    (
                        county,
                        code,
                        "district",
                        f"https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json",
                    )
                )
        time.sleep(0.2)
    fallback_codes = sorted(set(scopes) - found)
    if fallback_codes:
        client = AMapClient(Settings(), interval=0.5, retries=3)
        try:
            for code in fallback_codes:
                response = client.request(
                    DISTRICT_URL, {"keywords": code, "subdistrict": 0, "extensions": "all"}
                )
                root = next(
                    (
                        r
                        for r in response.body.get("districts", [])
                        if r.get("adcode") == code and r.get("level") == "district"
                    ),
                    None,
                )
                if not root or not root.get("polyline"):
                    raise ValueError(f"真实区县边界未返回：{code}")
                polygons = []
                for part in root["polyline"].split("|"):
                    ring = [
                        [float(v) for v in point.split(",")] for point in part.split(";") if point
                    ]
                    if len(ring) < 3:
                        raise ValueError("高德行政边界环坐标不足")
                    if ring[0] != ring[-1]:
                        ring.append(ring[0])
                    polygons.append([ring])
                feature = {
                    "type": "Feature",
                    "properties": {"adcode": code, "name": root["name"]},
                    "geometry": {"type": "MultiPolygon", "coordinates": polygons},
                }
                prepared.append((feature, scopes[code].city_code, "district", DISTRICT_URL))
                found.add(code)
        finally:
            client.close()
    if found != set(scopes):
        raise ValueError(f"真实区县边界不齐，缺失编码：{sorted(set(scopes) - found)}")
    invalid = []
    for feature, city_code, level, source in prepared:
        geometry = shape(feature["geometry"])
        if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("来源边界为空或不是面几何")
        code = str(feature["properties"]["adcode"])
        if not geometry.is_valid:
            invalid.append(code)
        row = session.get(AnalysisBoundary, code)
        if row is None:
            row = AnalysisBoundary(adcode=code)
            session.add(row)
        row.city_code = city_code
        row.name = feature["properties"]["name"]
        row.level = level
        row.geometry = feature["geometry"]
        row.source_url = source
        row.coordinate_system = "GCJ-02"
        row.content_hash = digest(feature["geometry"])
        row.fetched_at = utc_now()
    session.flush()
    return {
        "cities": 14,
        "districts": len(found),
        "amapFallbackCodes": fallback_codes,
        "invalidGeometryCodes": invalid,
        "notice": "来源几何保留原样；计算前必须显式检查/记录几何修复。",
    }


def main():
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session, session.begin():
            result = import_boundaries(session)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
