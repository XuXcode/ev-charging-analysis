"""Read-only local MySQL EXPLAIN and HTTP latency audit. Never writes business rows."""

import argparse
import gzip
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import get_settings
from app.db.session import create_db_engine

QUERIES = {
    "city_page": "SELECT id, poi_id, name, longitude, latitude FROM charging_stations WHERE source='amap' AND adcode LIKE '4301%' ORDER BY id LIMIT 200",
    "county_page": "SELECT id FROM charging_stations WHERE source='amap' AND adcode='430102' ORDER BY id LIMIT 200",
    "bbox_page": "SELECT id FROM charging_stations WHERE source='amap' AND adcode LIKE '4301%' AND longitude BETWEEN 112.9 AND 113.1 AND latitude BETWEEN 28.1 AND 28.3 ORDER BY id LIMIT 200",
    "classification_page": "SELECT s.id FROM poi_quality q JOIN charging_stations s ON s.id=q.station_id WHERE q.classification='personal' AND s.source='amap' ORDER BY s.id LIMIT 200",
    "review_status_page": "SELECT s.id FROM poi_quality q JOIN charging_stations s ON s.id=q.station_id WHERE q.review_status='confirmed' AND s.source='amap' ORDER BY s.id LIMIT 200",
    "collection_date": "SELECT COUNT(*), MAX(collected_at) FROM charging_stations WHERE source='amap' AND adcode LIKE '43%'",
    "ranking": "SELECT LEFT(adcode,4), COUNT(*) FROM charging_stations WHERE source='amap' AND adcode LIKE '43%' GROUP BY LEFT(adcode,4)",
    "statistics_latest": "SELECT MAX(statistic_date) FROM statistic_snapshots",
    "search_contains": "SELECT id FROM charging_stations WHERE source='amap' AND adcode LIKE '43%' AND (name LIKE '%特斯拉%' OR address LIKE '%特斯拉%' OR poi_id LIKE '%特斯拉%') ORDER BY id LIMIT 8",
    "search_count": "SELECT COUNT(*) FROM charging_stations WHERE source='amap' AND adcode LIKE '43%' AND (name LIKE '%特斯拉%' OR address LIKE '%特斯拉%' OR poi_id LIKE '%特斯拉%')",
    "review_clues": "SELECT s.id FROM charging_stations s JOIN poi_quality q ON q.station_id=s.id WHERE s.source='amap' AND q.needs_review=1 ORDER BY s.id LIMIT 200",
    "county_public": "SELECT s.id FROM charging_stations s JOIN poi_quality q ON q.station_id=s.id WHERE s.source='amap' AND s.adcode='430102' AND q.classification='public_candidate' ORDER BY s.id LIMIT 200",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="PERFORMANCE_DEEP_AUDIT.json",
        help="docs中的输出文件名，保留旧阶段报告",
    )
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        raise ValueError("仅允许docs中的JSON文件名")
    engine = create_db_engine(get_settings())
    report = {"generatedAt": datetime.now(UTC).isoformat(), "readOnly": True}
    schema = inspect(engine)
    tables = [
        "charging_stations",
        "poi_quality",
        "statistic_snapshots",
        "analysis_snapshots",
    ]
    report["indexes"] = {
        table: {
            "indexes": schema.get_indexes(table),
            "unique": schema.get_unique_constraints(table),
            "primary": schema.get_pk_constraint(table),
        }
        for table in tables
    }
    report["queries"] = {}
    with engine.connect() as connection:
        connection.exec_driver_sql("START TRANSACTION READ ONLY")
        report["rowCounts"] = {
            table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in tables
        }
        for name, sql in QUERIES.items():
            plan = [
                dict(row)
                for row in connection.execute(text("EXPLAIN " + sql)).mappings()
            ]
            times = []
            for _ in range(3):
                start = perf_counter()
                rows = connection.execute(text(sql)).all()
                times.append((perf_counter() - start) * 1000)
            report["queries"][name] = {
                "sql": sql,
                "plan": plan,
                "resultRows": len(rows),
                "medianMs": round(statistics.median(times), 2),
                "maxMs": round(max(times), 2),
            }
    report["http"] = {}
    for path in [
        "/dashboard",
        "/collection/summary",
        "/stations?city=430100&page_size=200",
        "/stations?city=430100&bbox=112.9,28.1,113.1,28.3&page_size=200",
        "/quality/pois?needs_review=true&page_size=30",
        "/analysis/latest",
        "/analysis/latest?classification=personal",
        "/analysis/layers/grid",
        "/analysis/latest?needs_review=true",
        "/stations?"
        + urlencode(
            {"keyword": "特斯拉", "classification": "public_candidate", "page_size": 8}
        ),
    ]:
        times = []
        for _ in range(3):
            start = perf_counter()
            request = Request(
                "http://127.0.0.1:8000/api/v1" + path,
                headers={"Accept-Encoding": "gzip"},
            )
            with urlopen(request, timeout=30) as response:
                body = response.read()
                encoding = response.headers.get("Content-Encoding", "identity")
                status = response.status
            payload = gzip.decompress(body) if encoding == "gzip" else body
            parsed = json.loads(payload)
            if "/analysis/latest" in path and "frozenInputs" in parsed.get("data", {}):
                raise ValueError("分析读取API不应发送冻结输入")
            times.append((perf_counter() - start) * 1000)
        report["http"][path] = {
            "status": status,
            "encoding": encoding,
            "wireBytes": len(body),
            "jsonBytes": len(payload),
            "medianMs": round(statistics.median(times), 2),
            "maxMs": round(max(times), 2),
        }
    output = ROOT / "docs/reports" / args.output
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "report": str(output),
                "rowCounts": report["rowCounts"],
                "queryMedianMs": {
                    k: v["medianMs"] for k, v in report["queries"].items()
                },
                "http": report["http"],
            },
            ensure_ascii=False,
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
