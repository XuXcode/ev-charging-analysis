from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.db.import_regions import import_regions
from app.db.session import get_session
from app.main import create_app
from app.models import ChargingStation
from app.repositories.data import RegionRepository, StationRepository
from app.schemas.data import StationCreate


def test_empty_database_has_no_generated_business_data(session, test_settings):
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        assert client.get("/api/v1/stations").json()["data"]["total"] == 0
        overview = client.get("/api/v1/overview").json()["data"]
        assert overview["metrics"][0]["value"] is None
        assert overview["sourceInfo"]["updatedAt"] is None
        assert not overview["sourceInfo"]["simulated"]
        assert client.get("/api/v1/dashboard").json()["data"]["trend"] == []


def test_collector_upsert_and_analysis_iteration(demo_session):
    existing = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    payload = StationCreate(
        poi_id=existing.poi_id,
        name="采集字段更新测试",
        address=existing.address,
        province=existing.province,
        city=existing.city,
        district=existing.district,
        adcode=existing.adcode,
        longitude=float(existing.longitude),
        latitude=float(existing.latitude),
        station_type=existing.station_type,
        source=existing.source,
        collected_at=datetime(2026, 9, 30),
        public_charger_count=12,
        data_source_id=existing.data_source_id,
    )
    repo = StationRepository(demo_session)
    result = repo.upsert_by_poi(payload)
    assert result.id == existing.id and result.name == "采集字段更新测试"
    assert demo_session.scalar(select(func.count()).select_from(ChargingStation)) == 42
    region = RegionRepository(demo_session).get("430100")
    assert len(list(repo.iter_for_region(region, batch_size=1))) == 3


def test_real_region_metadata_does_not_generate_statistics(session, test_settings):
    assert import_regions(session) == 15
    assert import_regions(session) == 15
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        data = client.get("/api/v1/dashboard").json()["data"]
        assert len(data["cities"]) == 14
        assert all(
            city["stations"] is None and city["density"] is None and not city["simulated"]
            for city in data["cities"]
        )
        assert data["stations"] == [] and data["trend"] == []
        assert data["analysisGroups"]["scale"][0]["key"] == "pending"
        assert len(data["analysisGroups"]["scale"][0]["cityCodes"]) == 14


def test_mysql_constraints_are_enforced(demo_session):
    row = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    with pytest.raises(DBAPIError) as error, demo_session.begin_nested():
        row.longitude = 181
        demo_session.flush()
    assert error.value.orig.args[0] == 3819


def test_committed_repository_change_stays_in_test_transaction(demo_session):
    row = demo_session.scalar(select(ChargingStation).order_by(ChargingStation.id))
    row.name = "transaction rollback test"
    demo_session.commit()
    assert (
        demo_session.scalar(select(ChargingStation.name).where(ChargingStation.id == row.id))
        == "transaction rollback test"
    )
