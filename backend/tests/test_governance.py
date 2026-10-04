from sqlalchemy import select

from app.models import AnalysisScopeQuality, ChargingStation, CollectionRun, PoiQuality
from app.services.governance import classify_poi


def test_public_is_only_candidate():
    result = classify_poi("汽车充电站", {"type": "汽车服务;充电站;充电站", "typecode": "011100"})
    assert result["classification"] == "public_candidate"
    assert result["confidence"] == "evidence_only"
    assert "未核验" in result["reasons"][0]["label"]


def test_closed_hint_overrides_personal_but_preserves_evidence():
    result = classify_poi(
        "汽车充电站(暂停营业)(已拆除)", {"type": "个人充电站", "typecode": "011104"}
    )
    assert result["classification"] == "suspected_closed"
    assert result["evidence"]["rawType"] == "个人充电站"
    assert result["needs_review"]
    assert len(result["reasons"]) == 3


def test_personal_and_dedicated_are_not_public():
    assert classify_poi("充电站", {"type": "个人充电站"})["classification"] == "personal"
    assert classify_poi("充电站", {"type": "专用充电站"})["classification"] == "dedicated"


def test_unknown_category_access_and_missing_evidence():
    for name, raw in [
        ("汽车充电站", {"type": "生活服务"}),
        ("内部专用充电站", {"type": "充电站", "typecode": "011100"}),
        ("充电站", None),
    ]:
        result = classify_poi(name, raw)
        assert result["classification"] == "unknown"
        assert result["needs_review"]


def test_ambiguous_vehicle_name_is_not_public():
    result = classify_poi("电动车充电站", {"type": "充电站", "typecode": "011100"})
    assert result["classification"] == "unknown"
    assert result["needs_review"]


def test_composite_category_has_its_own_traceable_reason():
    result = classify_poi("汽车充电站", {"type": "充电站", "typecode": "011100|011101"})
    assert result["classification"] == "unknown"
    assert "复合" in result["reasons"][0]["label"]
    assert "缺少" in classify_poi("汽车充电站", None)["reasons"][0]["label"]


def test_quality_api_filters_and_returns_trace(client, demo_session):
    station = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    station.source = "amap"
    station.adcode = "430102"
    run = CollectionRun(id="a" * 32, status="completed", manifest={})
    demo_session.add(run)
    demo_session.flush()
    demo_session.add(
        PoiQuality(
            station_id=station.id,
            classification="unknown",
            confidence="insufficient",
            reasons=[{"label": "原始类别待核验"}],
            evidence={},
            needs_review=True,
            review_status="unreviewed",
            rules_version="test-v1",
            run_id=run.id,
        )
    )
    demo_session.add(
        AnalysisScopeQuality(
            adcode="430102",
            city_code="430100",
            name="芙蓉区",
            completeness_warning=True,
            reason="检索上限",
            run_id=run.id,
        )
    )
    demo_session.flush()
    response = client.get("/api/v1/quality/pois?adcode=430100&classification=unknown")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["completenessWarning"]
    assert data["items"][0]["runId"] == run.id
    assert client.get("/api/v1/quality/pois?classification=personal").json()["data"]["total"] == 0
    assert client.get("/api/v1/quality/pois?page_size=101").status_code == 422
    assert client.get("/api/v1/quality/pois?adcode=440100").status_code == 422
