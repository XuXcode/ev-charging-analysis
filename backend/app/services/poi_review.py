"""Traceable review triage; no rule-based closure verdict or source deletion."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import ChargingStation, PoiQuality, PoiReviewEvent
from app.models.entities import utc_now
from app.services.analysis.job import digest


def append_event(session, station_id, kind, before, after, evidence, reason):
    identity = digest(
        {
            "stationId": station_id,
            "kind": kind,
            "before": before,
            "after": after,
            "evidence": evidence,
            "reason": reason,
        }
    )
    if session.scalar(select(PoiReviewEvent.id).where(PoiReviewEvent.event_hash == identity)):
        return False
    session.add(
        PoiReviewEvent(
            station_id=station_id,
            event_hash=identity,
            kind=kind,
            actor="automated_evidence_triage",
            before=before,
            after=after,
            evidence=evidence,
            reason=reason,
        )
    )
    return True


def triage_high_risk(session):
    rows = session.execute(
        select(PoiQuality, ChargingStation.poi_id)
        .join(ChargingStation)
        .where(
            ChargingStation.source == "amap",
            PoiQuality.classification.in_(["suspected_closed", "dedicated", "personal"]),
        )
    ).all()
    changes = []
    for quality, poi_id in rows:
        # Existing manual conclusions are preserved; triage cannot overwrite them.
        if quality.review_status != "unreviewed":
            continue
        before = {
            "reviewStatus": quality.review_status,
            "reviewNote": quality.review_note,
            "reviewedAt": quality.reviewed_at.isoformat() if quality.reviewed_at else None,
        }
        reason = "P0复核分流：原始类别或名称含停业/拆除、专用、个人线索；尚未核实营业或公共开放，需运营方或现场证据。"
        after = {
            "reviewStatus": "needs_review",
            "reviewNote": reason,
            "reviewedAt": before["reviewedAt"],
        }
        append_event(
            session,
            quality.station_id,
            "operating_access_triage",
            before,
            after,
            {
                "classification": quality.classification,
                "rulesVersion": quality.rules_version,
                "qualityBatch": quality.run_id,
                "basis": quality.evidence,
                "manualVerified": False,
            },
            reason,
        )
        quality.review_status = "needs_review"
        quality.review_note = reason
        # reviewed_at is reserved for an actual review, not an automated queue action.
        changes.append(
            {
                "stationId": quality.station_id,
                "poiId": poi_id,
                "classification": quality.classification,
                "before": before,
                "after": after,
            }
        )
    session.flush()
    return changes


def record_administrative_checks(session, baseline, provider):
    changes = []
    for record in baseline["records"]:
        observation = provider["records"].get(record["poiId"], {})
        if observation.get("status") != "ok":
            continue
        station = session.get(ChargingStation, record["stationId"])
        if (
            station is None
            or station.poi_id != record["poiId"]
            or station.adcode != record["sourceAdcode"]
        ):
            raise ValueError("当前站点身份或编码已变化，不能套用历史核验")
        if [float(station.longitude), float(station.latitude)] != record["position"]:
            raise ValueError("当前坐标与核验输入不一致")
        code = observation["addressComponent"].get("adcode")
        reason = (
            "二次高德逆地理编码与原始POI编码一致，保留原编码与坐标；DataV图形不一致需在边界版本层处理。"
            if code == station.adcode
            else "逆地理与原始编码不一致，待核对边界和运营方证据，暂不自动移址。"
        )
        before = {
            "adcode": station.adcode,
            "position": record["position"],
            "geometryAdcodes": record["geometryAdcodes"],
        }
        after = {
            **before,
            "providerAdcode": code,
            "decision": "source_code_reconfirmed" if code == station.adcode else "needs_review",
        }
        if append_event(
            session,
            station.id,
            "administrative_crosscheck",
            before,
            after,
            {
                "endpoint": provider["endpoint"],
                "observation": observation,
                "boundaryHashes": record["boundaryHashes"],
                "metricBoundaryDistanceM": record["sourceBoundaryDistanceM"],
            },
            reason,
        ):
            changes.append(
                {
                    "poiId": station.poi_id,
                    "stationId": station.id,
                    "before": before,
                    "after": after,
                    "reason": reason,
                }
            )
    session.flush()
    return changes


def main():
    parser = argparse.ArgumentParser(description="将核验与高风险复核分流写入追加式证据台账")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("需要--apply；此任务不会删除站点或确认停业")
    root = Path(__file__).resolve().parents[3]
    baseline = json.loads(
        (root / "docs/reports/ADMIN_REVIEW_BASELINE.json").read_text(encoding="utf-8")
    )
    provider = json.loads(
        (root / "docs/reports/ADMIN_REVIEW_PROVIDER.json").read_text(encoding="utf-8")
    )
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session, session.begin():
            administrative = record_administrative_checks(session, baseline, provider)
            high_risk = triage_high_risk(session)
        report = {
            "createdAt": utc_now().isoformat() + "Z",
            "administrative": administrative,
            "highRisk": high_risk,
            "notice": "自动证据复核/分流，不证明法律行政归属或营业状态；原始站点、坐标、采集页面未删除。",
        }
        target = root / "docs/reports/POI_REVIEW_CHANGES.json"
        if target.exists():
            target = root / f"docs/reports/POI_REVIEW_CHANGES_{utc_now():%Y%m%d%H%M%S}.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            {
                "administrativeEventsAdded": len(administrative),
                "highRiskQueued": len(high_risk),
                "report": target.name,
            }
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
