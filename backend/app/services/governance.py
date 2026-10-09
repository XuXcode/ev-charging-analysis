"""Conservative evidence classification, never an operating-status verdict."""

import json
from pathlib import Path

from sqlalchemy import select

from app.models import (
    AnalysisScopeQuality,
    ChargingStation,
    CollectionPage,
    CollectionRun,
    PoiQuality,
)
from app.models.entities import utc_now

RULES_VERSION = "poi-evidence-v1.1"
RULES = json.loads(
    (Path(__file__).resolve().parents[3] / "frontend/src/config/poi-quality-rules.json").read_text(
        encoding="utf-8"
    )
)
CLASSIFICATIONS = ("public_candidate", "dedicated", "personal", "suspected_closed", "unknown")


def classify_poi(name: str, raw: dict | None) -> dict:
    raw = raw or {}
    raw_type = str(raw.get("type") or "")
    code = str(raw.get("typecode") or "")
    hints = [
        {"group": group, "label": rule["label"]}
        for group, definitions in RULES.items()
        for rule in definitions
        if any(token in name for token in rule["tokens"])
    ]
    if raw and "充电站" not in raw_type:
        hints.append({"group": "category", "label": "原始类别未含充电站"})
    personal = "个人充电站" in raw_type
    dedicated = "专用充电站" in raw_type
    if personal or dedicated:
        hints.append({"group": "access", "label": "个人或专用类别，开放范围待核验"})
    if "暂停营业" in name or "已拆除" in name:
        classification = "suspected_closed"
    elif personal:
        classification = "personal"
    elif dedicated:
        classification = "dedicated"
    elif hints or not raw or code != "011100":
        classification = "unknown"
    else:
        classification = "public_candidate"
    return {
        "classification": classification,
        "confidence": "evidence_only" if raw else "insufficient",
        "reasons": hints
        or [
            {
                "group": "basis",
                "label": "缺少原始分类证据"
                if not raw
                else "原始类别编码缺失或复合，未判为公共候选"
                if code != "011100"
                else "原始类别为充电站，公共开放状态未核验",
            }
        ],
        "needs_review": bool(hints) or not raw,
        "evidence": {"name": name, "rawType": raw_type, "rawTypeCode": code},
        "rules_version": RULES_VERSION,
    }


def latest_province_run(session):
    runs = session.scalars(
        select(CollectionRun)
        .where(CollectionRun.status.in_(("completed", "completed_with_limits")))
        .order_by(CollectionRun.finished_at.desc())
    )
    run = next((row for row in runs if len(row.manifest.get("cities", [])) == 14), None)
    if run is None:
        raise ValueError("没有已完成的14市州真实采集批次")
    return run


def govern_pois(session):
    """Caller commits atomically; only derived quality tables are changed."""
    run = latest_province_run(session)
    raw_by_id = {}
    evidence_runs = {}
    capped = set()
    for page in session.scalars(
        select(CollectionPage)
        .where(CollectionPage.run_id == run.id)
        .order_by(CollectionPage.collected_at, CollectionPage.id)
    ):
        if page.capped:
            capped.add(page.adcode)
        for raw in page.raw_pois:
            if isinstance(raw, dict) and raw.get("id"):
                raw_by_id[raw["id"]] = raw
                evidence_runs[raw["id"]] = run.id
    # Supplement evidence applies only to newly inserted canonical stations.
    # Observations of an existing station must not rewrite its retained original evidence.
    for page in session.scalars(
        select(CollectionPage)
        .join(CollectionRun, CollectionRun.id == CollectionPage.run_id)
        .where(
            CollectionRun.manifest["version"].as_integer() == 2,
            CollectionRun.manifest["parentRunId"].as_string() == run.id,
        )
        .order_by(CollectionPage.collected_at, CollectionPage.id)
    ):
        for outcome in page.outcomes:
            if outcome["status"] != "inserted":
                continue
            raw = page.raw_pois[outcome["index"]]
            raw_by_id[outcome["poiId"]] = raw
            evidence_runs[outcome["poiId"]] = page.run_id
    for city_code, scopes in run.manifest.get("scopes", {}).items():
        for scope in scopes:
            row = session.get(AnalysisScopeQuality, scope["adcode"])
            if row is None:
                row = AnalysisScopeQuality(adcode=scope["adcode"])
                session.add(row)
            row.city_code = city_code
            row.name = scope["name"]
            row.run_id = run.id
            row.completeness_warning = scope["adcode"] in capped
            row.reason = (
                "高德检索触及200条返回上限，样本可能不完整" if row.completeness_warning else None
            )
    counts = {key: 0 for key in CLASSIFICATIONS}
    review_count = total = 0
    for station in session.scalars(
        select(ChargingStation).where(
            ChargingStation.source == "amap", ChargingStation.adcode.startswith("43")
        )
    ):
        decision = classify_poi(station.name, raw_by_id.get(station.poi_id))
        row = session.get(PoiQuality, station.id)
        if row is None:
            row = PoiQuality(station_id=station.id, review_status="unreviewed")
            session.add(row)
        # A repeated job must not silently overwrite a future human review.
        if row.review_status == "unreviewed":
            for key, value in decision.items():
                setattr(row, key, value)
            row.run_id = evidence_runs.get(station.poi_id, run.id)
            row.classified_at = utc_now()
        counts[row.classification] += 1
        review_count += int(row.needs_review)
        total += 1
    session.flush()
    return {
        "runId": run.id,
        "stationCount": total,
        "classifications": counts,
        "reviewCount": review_count,
        "cappedDistricts": len(capped),
        "rulesVersion": RULES_VERSION,
    }
