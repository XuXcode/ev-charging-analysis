"""Read-only profile of the actual station response path, without credentials or POI rows."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import get_settings
from app.db.session import create_db_engine
from app.services.data import DataService


def main():
    engine = create_db_engine(get_settings())
    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "readOnly": True,
        "cases": [],
    }
    for scope, bbox in [("city", None), ("bbox", (112.9, 28.1, 113.1, 28.3))]:
        for attempt in range(3):
            queries = []

            def before(conn, cursor, statement, parameters, context, many):
                context.audit_start = perf_counter()

            def after(
                conn, cursor, statement, parameters, context, many, observations=queries
            ):
                observations.append(
                    {
                        "sql": statement,
                        "executeMs": round(
                            (perf_counter() - context.audit_start) * 1000, 3
                        ),
                    }
                )

            with engine.connect() as connection:
                connection.exec_driver_sql("START TRANSACTION READ ONLY")
                event.listen(connection, "before_cursor_execute", before)
                event.listen(connection, "after_cursor_execute", after)
                try:
                    with Session(bind=connection) as session:
                        service = DataService(session)
                        start = perf_counter()
                        city = service.regions.get("430100")
                        rows, total = service.stations.page(
                            region=city,
                            bbox=bbox,
                            page=1,
                            page_size=200,
                            real_only=True,
                        )
                        page_ms = (perf_counter() - start) * 1000
                        start = perf_counter()
                        service.station_quality = service.stations.quality_for(rows)
                        quality_ms = (perf_counter() - start) * 1000
                        start = perf_counter()
                        items = [service.station_view(row) for row in rows]
                        serialize_ms = (perf_counter() - start) * 1000
                        start = perf_counter()
                        service.station_source_info(real_only=True)
                        source_ms = (perf_counter() - start) * 1000
                        report["cases"].append(
                            {
                                "scope": scope,
                                "attempt": attempt + 1,
                                "returned": len(items),
                                "total": total,
                                "pageMs": round(page_ms, 3),
                                "qualityMs": round(quality_ms, 3),
                                "serializeMs": round(serialize_ms, 3),
                                "sourceMs": round(source_ms, 3),
                                "queryCount": len(queries),
                                "queries": queries,
                            }
                        )
                finally:
                    event.remove(connection, "before_cursor_execute", before)
                    event.remove(connection, "after_cursor_execute", after)
                    connection.rollback()
    engine.dispose()
    target = ROOT / "docs/reports" / "STATION_RESPONSE_PROFILE.json"
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for case in report["cases"]:
        print(json.dumps({k: v for k, v in case.items() if k != "queries"}))


if __name__ == "__main__":
    main()
