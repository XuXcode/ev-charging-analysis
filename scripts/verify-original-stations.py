"""Verify the protected station rows against the stored pre-development baseline."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend"))
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.session import create_db_engine, create_session_factory
    from app.models import ChargingStation

    baseline_path = root / "docs/reports/POI_PRESERVATION_BASELINE.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    digest, count = hashlib.sha256(), 0
    engine = create_db_engine(get_settings())
    try:
        with create_session_factory(engine)() as session:
            for row in session.execute(
                select(ChargingStation.__table__).order_by(ChargingStation.id)
            ):
                digest.update(
                    json.dumps(
                        dict(row._mapping),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
                count += 1
    finally:
        engine.dispose()
    report = {
        "verifiedAt": datetime.now(UTC).isoformat(),
        "stationCount": count,
        "stationRowsSha256": digest.hexdigest(),
        "baselineStationCount": baseline["chargingStationCount"],
        "baselineStationRowsSha256": baseline["chargingStationRowsSha256"],
        "matched": count == baseline["chargingStationCount"]
        and digest.hexdigest() == baseline["chargingStationRowsSha256"],
        "databaseWrites": 0,
        "providerCalls": 0,
        "notice": "All stored station columns compared; does not validate truth or completeness of provider POIs.",
    }
    (root / "docs/reports/ORIGINAL_POI_PRESERVATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))
    if not report["matched"]:
        raise SystemExit("原始站点与保护基线不同，先核验，不继续导入或覆盖")


if __name__ == "__main__":
    main()
