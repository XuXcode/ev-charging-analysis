from sqlalchemy import func, select

from app.models import ChargingStation, CollectionRun, PoiQuality, PoiReviewEvent
from app.services.poi_review import record_administrative_checks, triage_high_risk


def setup_station(session):
    station = session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    station.source, station.adcode, station.poi_id = "amap", "430102", "TEST-REVIEW"
    run = CollectionRun(id="e" * 32, status="completed", manifest={})
    session.add(run)
    session.flush()
    quality = PoiQuality(
        station_id=station.id,
        classification="suspected_closed",
        confidence="evidence_only",
        reasons=[],
        evidence={"name": "测试停业线索"},
        needs_review=True,
        review_status="unreviewed",
        rules_version="test-only",
        run_id=run.id,
    )
    session.add(quality)
    session.flush()
    return station, quality


def test_triage_is_traceable_idempotent_and_preserves_manual_decisions(client, demo_session):
    station, quality = setup_station(demo_session)
    before = (
        station.name,
        station.longitude,
        station.latitude,
        station.adcode,
        station.collected_at,
    )
    assert len(triage_high_risk(demo_session)) == 1
    assert quality.review_status == "needs_review" and quality.reviewed_at is None
    assert len(triage_high_risk(demo_session)) == 0
    assert demo_session.scalar(select(func.count()).select_from(PoiReviewEvent)) == 1
    assert before == (
        station.name,
        station.longitude,
        station.latitude,
        station.adcode,
        station.collected_at,
    )
    quality.review_status, quality.review_note = "confirmed", "人工证据说明"
    assert triage_high_risk(demo_session) == []
    assert quality.review_note == "人工证据说明"
    response = client.get(f"/api/v1/quality/pois/{station.id}/reviews")
    assert response.status_code == 200
    event = response.json()["data"]["items"][0]
    assert event["before"]["reviewStatus"] == "unreviewed"
    assert event["after"]["reviewStatus"] == "needs_review"
    assert event["evidence"]["manualVerified"] is False


def test_administrative_confirmation_keeps_original_coordinates_and_code(demo_session):
    station, _ = setup_station(demo_session)
    position = [float(station.longitude), float(station.latitude)]
    baseline = {
        "records": [
            {
                "stationId": station.id,
                "poiId": station.poi_id,
                "sourceAdcode": station.adcode,
                "position": position,
                "geometryAdcodes": ["430103"],
                "boundaryHashes": {"430103": "test-only"},
                "sourceBoundaryDistanceM": 10,
            }
        ]
    }
    provider = {
        "endpoint": "https://restapi.amap.com/v3/geocode/regeo",
        "records": {
            station.poi_id: {"status": "ok", "addressComponent": {"adcode": station.adcode}}
        },
    }
    result = record_administrative_checks(demo_session, baseline, provider)
    assert len(result) == 1 and result[0]["after"]["decision"] == "source_code_reconfirmed"
    assert station.adcode == "430102"
    assert [float(station.longitude), float(station.latitude)] == position
    assert record_administrative_checks(demo_session, baseline, provider) == []
