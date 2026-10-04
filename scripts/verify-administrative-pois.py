"""49-point AMap reverse-geocode evidence only; never edits source stations."""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402

ENDPOINT = "https://restapi.amap.com/v3/geocode/regeo"


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description="行政不一致POI逆地理核验，原始记录不变")
    parser.add_argument("--limit", type=int, default=49)
    args = parser.parse_args()
    if not 1 <= args.limit <= 49:
        parser.error("核验最多49次，不自动增加额度")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = Settings()
    if not settings.amap_webservice_key:
        parser.error("未配置Web Service Key")
    baseline = json.loads((ROOT / "docs/reports/ADMIN_REVIEW_BASELINE.json").read_text(encoding="utf-8"))
    path = ROOT / "docs/reports/ADMIN_REVIEW_PROVIDER.json"
    report = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"endpoint": ENDPOINT, "coordinateSystem": "GCJ-02", "reservedCalls": 0, "records": {}}
    )
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        for record in baseline["records"]:
            identity = record["poiId"]
            if identity in report["records"]:
                continue
            if report["reservedCalls"] >= args.limit:
                break
            location = ",".join(f"{v:.6f}" for v in record["position"])
            # Conservative reservation persists before network; no reset after interruption.
            report["reservedCalls"] += 1
            write(path, report)
            try:
                response = client.get(
                    ENDPOINT,
                    params={
                        "key": settings.amap_webservice_key.get_secret_value(),
                        "location": location,
                        "extensions": "base",
                        "output": "JSON",
                    },
                )
                response.raise_for_status()
                body = response.json()
                component = body.get("regeocode", {}).get("addressComponent", {})
                if body.get("status") != "1" or not isinstance(component, dict):
                    raise ValueError
                evidence = {"status": "ok", "addressComponent": component}
            except (httpx.HTTPError, ValueError, AttributeError):
                evidence = {
                    "status": "failed",
                    "reason": "未取得有效逆地理结果；不输出请求URL或上游错误",
                }
            report["records"][identity] = {
                "stationId": record["stationId"],
                "requestLocation": location,
                "observedAt": datetime.now(UTC).isoformat(),
                **evidence,
            }
            write(path, report)
            if evidence["status"] == "failed":
                break
            time.sleep(1)
    records = report["records"]
    print(
        {
            "reservedCalls": report["reservedCalls"],
            "observations": len(records),
            "successful": sum(r["status"] == "ok" for r in records.values()),
            "output": path.name,
        }
    )


if __name__ == "__main__":
    main()
