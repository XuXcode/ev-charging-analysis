"""Read-only audit of existing POI evidence; never collect, delete or update stations."""

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402
from app.db.session import create_db_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

BOUNDARY_URL = "https://geo.datav.aliyun.com/areas_v3/bound/430000_full.json"


def iso_utc(value):
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


def signals(name, rules):
    return [rule["label"] for rule in rules if any(token in name for token in rule["tokens"])]


def canonical_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def audit_boundary(verify_source):
    boundary = json.loads((ROOT / "src/assets/hunan.geojson.json").read_text(encoding="utf-8"))
    features = boundary["features"]
    invalid_coordinates = unclosed_rings = 0
    points = []
    for feature in features:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                unclosed_rings += int(len(ring) < 4 or ring[0] != ring[-1])
                for point in ring:
                    if len(point) != 2 or not all(math.isfinite(v) for v in point):
                        invalid_coordinates += 1
                    elif not (108 < point[0] < 115 and 24 < point[1] < 31):
                        invalid_coordinates += 1
                    else:
                        points.append(point)
    codes = [str(feature["properties"]["adcode"]) for feature in features]
    result = {
        "sourceUrl": BOUNDARY_URL,
        "coordinateSystem": "GCJ-02",
        "coordinateBasis": "供应方文档与来源链路，非逐点实地配准",
        "sha256": canonical_hash(boundary),
        "featureCount": len(features),
        "cityCodes": codes,
        "uniqueCityCodeCount": len(set(codes)),
        "vertexCount": len(points),
        "invalidCoordinates": invalid_coordinates,
        "unclosedRings": unclosed_rings,
        "bbox": [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)],
        "providerComparison": "未请求供应方边界",
    }
    if verify_source:
        try:
            with urlopen(BOUNDARY_URL, timeout=20) as response:
                remote = json.load(response)
            result["providerComparison"] = "内容一致" if canonical_hash(remote) == result["sha256"] else "内容存在差异，未替换本地边界"
            result["providerSha256"] = canonical_hash(remote)
        except Exception as error:
            result["providerComparison"] = f"无法验证在线版本（{type(error).__name__}），保留本地版本"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-boundary-source", action="store_true")
    args = parser.parse_args()
    rules = json.loads((ROOT / "src/config/poi-quality-rules.json").read_text(encoding="utf-8"))
    engine = create_db_engine(Settings())
    # Read-only transaction is enforced by MySQL in addition to SELECT-only code.
    with engine.connect() as connection:
        connection.exec_driver_sql("START TRANSACTION READ ONLY")
        stations = connection.execute(text("SELECT id,poi_id,name,adcode,longitude,latitude,source,collected_at,station_type,public_charger_count,identity_hash FROM charging_stations WHERE source='amap' ORDER BY id")).mappings().all()
        runs = connection.execute(text("SELECT id,manifest FROM collection_runs WHERE status IN ('completed','completed_with_limits') ORDER BY finished_at DESC")).mappings().all()
        run = next((row for row in runs if len(json.loads(row["manifest"]).get("cities", [])) == 14), None)
        pages = connection.execute(text("SELECT raw_pois FROM collection_pages WHERE run_id=:run_id ORDER BY collected_at,id"), {"run_id": run["id"]}).scalars().all() if run else []
        supplement_ids = [row["id"] for row in runs if json.loads(row["manifest"]).get("parentRunId") == (run["id"] if run else None) and json.loads(row["manifest"]).get("version") == 2]
        supplements = []
        for supplement_id in supplement_ids:
            supplements.extend(connection.execute(text("SELECT raw_pois,outcomes FROM collection_pages WHERE run_id=:run_id ORDER BY collected_at,id"), {"run_id": supplement_id}).mappings().all())
        connection.rollback()
    engine.dispose()
    raw_by_id = {}
    for page in pages:
        for poi in json.loads(page):
            if isinstance(poi, dict) and poi.get("id"):
                raw_by_id[poi["id"]] = poi
    for page in supplements:
        raw = json.loads(page["raw_pois"])
        for outcome in json.loads(page["outcomes"]):
            if outcome["status"] == "inserted":
                raw_by_id[outcome["poiId"]] = raw[outcome["index"]]
    types = Counter()
    status_counts = Counter()
    access_counts = Counter()
    category_counts = Counter()
    city_counts = Counter()
    review = []
    invalid_coordinates = missing_trace = unmatched_raw = raw_non_charging = paused_removed = 0
    raw_personal = raw_dedicated = 0
    for station in stations:
        name = station["name"]
        city_code = station["adcode"][:4] + "00"
        city_counts[city_code] += 1
        status = signals(name, rules["status"])
        access = signals(name, rules["access"])
        category = signals(name, rules["category"])
        status_counts.update(status)
        access_counts.update(access)
        category_counts.update(category)
        paused_removed += int("暂停营业" in name or "已拆除" in name)
        invalid_coordinates += int(not (108 < float(station["longitude"]) < 115 and 24 < float(station["latitude"]) < 31))
        missing_trace += int(not all(station[key] for key in ("poi_id", "identity_hash", "source", "collected_at")))
        raw = raw_by_id.get(station["poi_id"])
        raw_type = str(raw.get("type") or "") if raw else ""
        raw_code = str(raw.get("typecode") or "") if raw else ""
        unmatched_raw += int(raw is None)
        types[(raw_code, raw_type)] += 1
        if raw and "充电站" not in raw_type:
            raw_non_charging += 1
            category.append("原始类别未含充电站")
        if "个人充电站" in raw_type:
            raw_personal += 1
            category.append("原始类别为个人充电站，开放范围待核验")
        if "专用充电站" in raw_type:
            raw_dedicated += 1
            category.append("原始类别为专用充电站，开放范围待核验")
        flags = status + access + category
        if flags:
            review.append({"poiId": station["poi_id"], "cityCode": city_code, "name": name, "adcode": station["adcode"], "rawTypeCode": raw_code, "rawType": raw_type, "hints": "；".join(flags), "collectedAt": iso_utc(station["collected_at"]), "verification": "名称或类别线索，尚未人工核验"})
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sourceUpdatedAt": iso_utc(max((s["collected_at"] for s in stations), default=None)),
        "stationCount": len(stations),
        "runId": run["id"] if run else None,
        "supplementRunIds": supplement_ids,
        "readOnly": True,
        "statusHints": dict(status_counts),
        "pausedOrRemovedUniqueCount": paused_removed,
        "accessHints": dict(access_counts),
        "categoryHints": dict(category_counts),
        "rawTypeNotChargingCount": raw_non_charging,
        "rawPersonalChargingCount": raw_personal,
        "rawDedicatedChargingCount": raw_dedicated,
        "unmatchedRawCount": unmatched_raw,
        "missingTraceCount": missing_trace,
        "invalidCoordinateCount": invalid_coordinates,
        "reviewUniqueCount": len(review),
        "cities": dict(city_counts),
        "rawTypes": [{"typeCode": code, "type": label, "count": count} for (code, label), count in types.most_common()],
        "storedTypes": dict(Counter(s["station_type"] for s in stations)),
        "boundary": audit_boundary(args.verify_boundary_source),
        "notice": "离线只读核验快照；名称与原始类别仅提供复核线索，不判定真实营业状态或车辆类型。重叠线索不能相加推算无效总量，所有样本均保留。",
    }
    output = ROOT / "public/data-quality"
    output.mkdir(parents=True, exist_ok=True)
    (output / "poi-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review_path = ROOT / "docs/data-quality/poi-review.csv"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["poiId", "cityCode", "name", "adcode", "rawTypeCode", "rawType", "hints", "collectedAt", "verification"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review)
    print(json.dumps({key: value for key, value in report.items() if key not in ("boundary", "cities", "storedTypes")}, ensure_ascii=False, indent=2))
    print(json.dumps({"boundary": report["boundary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
