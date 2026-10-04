"""Read-only baseline plus one real polygon permission probe; no station writes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisBoundary, AnalysisScopeQuality, ChargingStation
from app.models.entities import utc_now
from app.services.collector.client import AMapClient, CollectionError


def main():
    settings = Settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session:
            scopes = list(
                session.scalars(
                    select(AnalysisScopeQuality)
                    .where(AnalysisScopeQuality.completeness_warning.is_(True))
                    .order_by(AnalysisScopeQuality.adcode)
                )
            )
            counts = dict(
                session.execute(
                    select(ChargingStation.adcode, func.count())
                    .where(ChargingStation.source == "amap")
                    .group_by(ChargingStation.adcode)
                ).all()
            )
            result = {
                "recordedAt": utc_now().isoformat() + "Z",
                "stationWrites": 0,
                "districts": [
                    {
                        "adcode": row.adcode,
                        "name": row.name,
                        "beforeCount": counts.get(row.adcode, 0),
                        "status": "补采尚未执行",
                    }
                    for row in scopes
                ],
            }
            if not scopes:
                raise RuntimeError("没有待补采区县")
            row = session.get(AnalysisBoundary, scopes[0].adcode)
            from shapely.geometry import shape

            west, south, east, north = shape(row.geometry).bounds
            bounds = (west, south, (west + east) / 2, (south + north) / 2)
        client = AMapClient(settings, retries=1)
        try:
            pois, attempts = client.polygon_pois(bounds, 1)
            result["probe"] = {
                "adcode": scopes[0].adcode,
                "bounds": bounds,
                "returnedCount": len(pois),
                "attempts": attempts,
                "permissionVerified": True,
            }
        except CollectionError as failure:
            result["probe"] = {"permissionVerified": False, "error": str(failure)}
        finally:
            client.close()
        destination = Path(__file__).resolve().parents[1] / "docs/reports/SUPPLEMENT_BASELINE.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"districtCount": len(scopes), "probe": result["probe"], "stationWrites": 0},
                ensure_ascii=True,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
