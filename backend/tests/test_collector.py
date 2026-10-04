"""Synthetic transport fixtures live exclusively in the isolated test database."""

from contextlib import contextmanager
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.import_regions import import_regions
from app.db.session import get_session
from app.main import create_app
from app.models import ChargingStation, CollectionPage, CollectionRun, StatisticSnapshot
from app.models.entities import utc_now
from app.services.collector import runner
from app.services.collector.cleaning import clean_poi
from app.services.collector.client import AMapClient, CollectionError

SCOPE = {"adcode": "430102", "name": "芙蓉区", "cityCode": "430100"}


def poi(poi_id="test-poi", name="测试汽车充电站", location="112.980001,28.180001", **fields):
    return {
        "id": poi_id,
        "name": name,
        "location": location,
        "adcode": "430102",
        "type": "汽车服务;充电站",
        **fields,
    }


@pytest.fixture
def collector_db(session):
    import_regions(session)
    session.commit()
    return sessionmaker(
        bind=session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )


def new_run(factory):
    with factory.begin() as db:
        return runner.create_run(db, city_codes=["430100"])


class FakeClient:
    def __init__(self, pages=None):
        self.calls = []
        self.pages = pages or {}

    def districts(self, city_code):
        self.calls.append(("districts", city_code))
        return [SCOPE]

    def pois(self, code, page):
        self.calls.append((code, page))
        result = self.pages.get(page, [])
        if isinstance(result, Exception):
            raise result
        return result, 1


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"id": ""}, "missing_identity"),
        ({"name": ""}, "missing_identity"),
        ({"adcode": "440102"}, "outside_requested_district"),
        ({"adcode": "430103"}, "outside_requested_district"),
        ({"name": "自行车充电站"}, "not_ev_charging_station"),
        ({"location": "nan,28"}, "invalid_fields_or_coordinates"),
        ({"location": "112,inf"}, "invalid_fields_or_coordinates"),
        ({"location": "0,0"}, "invalid_fields_or_coordinates"),
        ({"location": "1,2"}, "implausible_hunan_coordinates"),
        ({"location": "not a point"}, "invalid_fields_or_coordinates"),
    ],
)
def test_clean_rejects(fields, reason):
    value, error = clean_poi(poi(**fields), SCOPE, "长沙市", 1, utc_now())
    assert value is None and error == reason


def test_dedup_and_provenance(collector_db):
    run_id = new_run(collector_db)
    client = FakeClient(
        {
            1: [
                poi(),
                poi(),
                poi("alternate-id", name="测试 汽车充电站"),
                poi("bad", location="nan,28"),
            ]
        }
    )
    runner.execute(collector_db, run_id, client)
    with collector_db() as db:
        assert db.scalar(select(func.count()).select_from(ChargingStation)) == 1
        row = db.scalar(select(ChargingStation))
        assert row.poi_id == "test-poi" and row.source == "amap"
        assert row.collected_at and row.identity_hash and row.public_charger_count is None
        assert db.scalar(select(func.count()).select_from(StatisticSnapshot)) == 0
        page = db.scalar(select(CollectionPage))
        assert page.raw_pois[2]["id"] == "alternate-id" and len(page.response_hash) == 64
        report = runner.report_run(db, db.get(CollectionRun, run_id))
        assert report["totals"] == {
            "rawCount": 4,
            "uniqueCount": 1,
            "duplicateCount": 2,
            "rejectedCount": 1,
            "insertedCount": 1,
            "updatedCount": 1,
            "mergedCount": 1,
            "committedPages": 1,
        }
    second_id = new_run(collector_db)
    runner.execute(collector_db, second_id, FakeClient({1: [poi()]}))
    with collector_db() as db:
        report = runner.report_run(db, db.get(CollectionRun, second_id))
        assert report["totals"]["insertedCount"] == 0
        assert report["totals"]["updatedCount"] == 1
        assert db.scalar(select(func.count()).select_from(ChargingStation)) == 1


def test_resume_skips_committed_pages(collector_db):
    run_id = new_run(collector_db)
    initial = FakeClient({1: [poi()] * 25, 2: CollectionError("测试网络中断")})
    with pytest.raises(CollectionError):
        runner.execute(collector_db, run_id, initial)
    with collector_db() as db:
        assert db.get(CollectionRun, run_id).status == "failed"
        assert db.scalar(select(func.count()).select_from(CollectionPage)) == 1
    resumed = FakeClient({2: [poi("second", location="112.9801,28.1801")]})
    runner.execute(collector_db, run_id, resumed)
    assert resumed.calls == [("430102", 2)]
    with collector_db() as db:
        report = runner.report_run(db, db.get(CollectionRun, run_id))
        assert report["status"] == "completed"
        assert report["totals"]["rawCount"] == 26 and report["totals"]["uniqueCount"] == 2
        assert report["totals"]["duplicateCount"] == 24
    runner.execute(collector_db, run_id, resumed)
    assert resumed.calls == [("430102", 2)]  # completed run performs no requests


def test_page_transaction_rollback(collector_db, monkeypatch):
    run_id = new_run(collector_db)
    original = runner.persist_page

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise CollectionError("测试提交前中断")

    monkeypatch.setattr(runner, "persist_page", fail_after_flush)
    with pytest.raises(CollectionError):
        runner.execute(collector_db, run_id, FakeClient({1: [poi()]}))
    with collector_db() as db:
        assert db.scalar(select(func.count()).select_from(ChargingStation)) == 0
        assert db.scalar(select(func.count()).select_from(CollectionPage)) == 0
    monkeypatch.setattr(runner, "persist_page", original)
    runner.execute(collector_db, run_id, FakeClient({1: [poi()]}))
    with collector_db() as db:
        assert db.scalar(select(func.count()).select_from(ChargingStation)) == 1


def test_cap_is_reported_without_ninth_page(collector_db):
    run_id = new_run(collector_db)
    pages = {
        page: [poi(f"p-{page}-{i}", name=f"测试{i + page * 25}充电站") for i in range(25)]
        for page in range(1, 9)
    }
    client = FakeClient(pages)
    runner.execute(collector_db, run_id, client)
    assert ("430102", 9) not in client.calls
    with collector_db() as db:
        report = runner.report_run(db, db.get(CollectionRun, run_id))
        assert report["status"] == "completed_with_limits"
        assert report["cappedDistricts"] == ["430102"]
        assert report["totals"]["uniqueCount"] == 200


@contextmanager
def transport_client(settings, handler, **kwargs):
    configured = settings.model_copy(update={"amap_webservice_key": SecretStr("test-only-secret")})
    client = AMapClient(configured, transport=httpx.MockTransport(handler), **kwargs)
    try:
        yield client
    finally:
        client.close()


def test_rate_limit_and_transient_retry(test_settings, caplog):
    now = [0.0]
    called_at = []

    def sleep(seconds):
        now[0] += seconds

    def handler(request):
        called_at.append(now[0])
        if len(called_at) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"status": "1", "pois": []})

    with transport_client(test_settings, handler, sleep=sleep, clock=lambda: now[0]) as client:
        assert client.pois("430102", 1) == ([], 2)
        assert client.pois("430102", 2) == ([], 1)
    assert all(b - a >= 1.0 for a, b in zip(called_at, called_at[1:], strict=False))
    assert "test-only-secret" not in caplog.text


def test_bad_key_is_not_retried_or_logged(test_settings, caplog):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200, json={"status": "0", "infocode": "10001", "info": "test-only-secret"}
        )

    with (
        transport_client(test_settings, handler) as client,
        pytest.raises(CollectionError) as error,
    ):
        client.pois("430102", 1)
    assert len(calls) == 1 and "10001" in str(error.value)
    assert "test-only-secret" not in str(error.value) + caplog.text


def test_timeout_exhaustion_sanitized(test_settings):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("test-only-secret", request=request)

    with transport_client(test_settings, handler, retries=2, sleep=lambda _: None) as client:
        with pytest.raises(CollectionError) as error:
            client.pois("430102", 1)
    assert len(calls) == 3 and "test-only-secret" not in str(error.value)


def test_real_api_defaults_exclude_demo(client):
    response = client.get("/api/v1/stations").json()["data"]
    assert response["items"] == [] and response["total"] == 0
    assert not response["sourceInfo"]["simulated"]
    summary = client.get("/api/v1/collection/summary").json()["data"]
    assert summary["storedCount"] == 0 and summary["latestRun"] is None


def test_no_missing_key_request(test_settings):
    with pytest.raises(CollectionError, match="尚未配置"):
        AMapClient(test_settings.model_copy(update={"amap_webservice_key": None}))


def test_persisted_station_api_and_quality(collector_db, test_settings):
    run_id = new_run(collector_db)
    runner.execute(
        collector_db, run_id, FakeClient({1: [poi(), poi("second", name="另一测试充电站")]})
    )
    application = create_app(test_settings.model_copy(deep=True))

    def database():
        with collector_db() as db:
            yield db

    application.dependency_overrides[get_session] = database
    with TestClient(application) as client:
        first = client.get("/api/v1/stations?city=430100&page_size=1").json()["data"]
        second = client.get("/api/v1/stations?city=430100&page_size=1&page=2").json()["data"]
        assert first["total"] == 2 and first["items"][0]["id"] != second["items"][0]["id"]
        assert client.get("/api/v1/stations?adcode=430102").json()["data"]["total"] == 2
        assert client.get("/api/v1/stations?adcode=430103").json()["data"]["total"] == 0
        assert client.get("/api/v1/stations?adcode=430102&city=430200").status_code == 422
        assert not first["items"][0]["simulated"]
        assert first["sourceInfo"]["updatedAt"].endswith("Z")
        assert first["items"][0]["collectedAt"].endswith("Z")
        assert client.get("/api/v1/stations?city=430200").json()["data"]["total"] == 0
        assert client.get("/api/v1/regions/430100").json()["data"]["stations"] is None
        assert client.get("/api/v1/trends").json()["data"]["items"] == []
        summary = client.get("/api/v1/collection/summary").json()["data"]
        assert summary["storedCount"] == 2 and len(summary["cities"]) == 14
        assert summary["latestRun"]["id"] == run_id
        assert (
            client.get(f"/api/v1/collection/runs/{run_id}").json()["data"]["totals"]["uniqueCount"]
            == 2
        )
        assert client.get("/api/v1/collection/runs/" + "0" * 32).status_code == 404


def test_all_fourteen_cities_have_independent_counts(collector_db):
    class CitiesClient:
        def districts(self, city_code):
            return [{"adcode": city_code[:4] + "02", "cityCode": city_code, "name": "测试区县"}]

        def pois(self, code, page):
            return [poi(code, name=f"测试{code}充电站", adcode=code)], 1

    with collector_db.begin() as db:
        run_id = runner.create_run(db)
    runner.execute(collector_db, run_id, CitiesClient())
    with collector_db() as db:
        report = runner.report_run(db, db.get(CollectionRun, run_id))
        assert report["totals"]["rawCount"] == report["totals"]["uniqueCount"] == 14
        assert len(report["cities"]) == 14 and all(c["uniqueCount"] == 1 for c in report["cities"])
        summary = runner.collection_summary(db)
        assert summary["storedCount"] == 14 and all(
            c["storedCount"] == 1 for c in summary["cities"]
        )


def test_summary_shows_resumed_batch_over_newer_trial(collector_db):
    older, trial = new_run(collector_db), new_run(collector_db)
    now = utc_now()
    with collector_db.begin() as db:
        old_run = db.get(CollectionRun, older)
        old_run.started_at = now - timedelta(days=1)
        old_run.updated_at = now
        old_run.status = "running"
        trial_run = db.get(CollectionRun, trial)
        trial_run.started_at = now - timedelta(minutes=1)
        trial_run.updated_at = now - timedelta(seconds=30)
        trial_run.status = "completed"
    with collector_db() as db:
        summary = runner.collection_summary(db)
        assert summary["latestRun"]["id"] == older
        assert summary["latestRun"]["status"] == "running"


def test_provider_district_discovery(test_settings):
    def handler(request):
        assert request.url.params["keywords"] == "430100"
        assert request.url.params["subdistrict"] == "1"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "districts": [
                    {
                        "adcode": "430100",
                        "districts": [
                            {"adcode": "430102", "name": "芙蓉区", "level": "district"},
                        ],
                    }
                ],
            },
        )

    with transport_client(test_settings, handler) as client:
        assert client.districts("430100") == [SCOPE]


@pytest.mark.parametrize(
    "roots",
    [
        [],
        [{"adcode": "430100", "districts": []}],
        [
            {
                "adcode": "430100",
                "districts": [{"adcode": "440102", "level": "district", "name": "外省"}],
            }
        ],
    ],
)
def test_provider_invalid_districts_are_not_silently_completed(test_settings, roots):
    with transport_client(
        test_settings, lambda _: httpx.Response(200, json={"status": "1", "districts": roots})
    ) as client:
        with pytest.raises(CollectionError):
            client.districts("430100")


def test_supplement_retains_original_station_and_historical_raw(collector_db):
    run_id = new_run(collector_db)
    with collector_db.begin() as db:
        first = runner.persist_page(db, run_id, SCOPE, "长沙市", 1, [poi()], 1)
        row = db.get(ChargingStation, first.outcomes[0]["stationId"])
        original = (row.name, row.longitude, row.latitude, row.collected_at)
        second = runner.persist_page(
            db,
            run_id,
            SCOPE,
            "长沙市",
            9,
            [poi(name="新名称汽车充电站", location="112.990001,28.190001")],
            1,
            preserve_existing=True,
            terminal_override=True,
            capped_override=False,
        )
        assert second.outcomes[0]["status"] == "retained"
        assert (row.name, row.longitude, row.latitude, row.collected_at) == original
        assert first.raw_pois[0]["name"] != second.raw_pois[0]["name"]
        assert second.terminal and not second.capped


def test_polygon_transport_has_bounded_pages_and_recorded_query(test_settings):
    def handler(request):
        assert request.url.path == "/v5/place/polygon"
        assert request.url.params["polygon"] == "112.900000,28.200000|113.000000,28.100000"
        assert request.url.params["types"] == "011100"
        assert request.url.params["page_num"] == "2"
        return httpx.Response(200, json={"status": "1", "pois": [poi()]})

    with transport_client(test_settings, handler) as client:
        rows, attempts = client.polygon_pois((112.9, 28.1, 113, 28.2), 2)
        assert len(rows) == 1 and attempts == 1
        with pytest.raises(CollectionError):
            client.polygon_pois((113, 28.1, 112.9, 28.2), 1)


def test_adaptive_supplement_splits_capped_shard_and_resumes_committed_page(collector_db):
    from shapely.geometry import box, mapping

    from app.models import AnalysisBoundary
    from app.services.analysis.job import digest
    from app.services.collector.supplement import execute_supplement, supplement_report

    run_id = "e" * 32
    geometry = mapping(box(112.9, 28.1, 113, 28.2))
    boundary_hash = digest(geometry)
    with collector_db.begin() as db:
        db.add(
            AnalysisBoundary(
                adcode="430102",
                city_code="430100",
                name="芙蓉区",
                level="district",
                geometry=geometry,
                source_url="https://test.invalid/boundary",
                coordinate_system="GCJ-02",
                content_hash=boundary_hash,
            )
        )
        db.add(
            CollectionRun(
                id=run_id,
                status="pending",
                manifest={
                    "version": 2,
                    "strategy": "adaptive_polygon_v1",
                    "parentRunId": run_id,
                    "maxDepth": 2,
                    "minSpanDegrees": 0.002,
                    "notice": "test",
                    "targets": [
                        {
                            **SCOPE,
                            "cityName": "长沙市",
                            "beforeCount": 0,
                            "boundaryHash": boundary_hash,
                        }
                    ],
                    "shards": [
                        {
                            "index": 0,
                            "adcode": "430102",
                            "bounds": [112.9, 28.1, 113, 28.2],
                            "depth": 0,
                            "status": "pending",
                        }
                    ],
                },
            )
        )

    class Provider:
        def __init__(self, fail=False):
            self.calls = []
            self.fail = fail

        def polygon_pois(self, bounds, page):
            self.calls.append((bounds, page))
            if self.fail and page == 2:
                raise CollectionError("可恢复的测试故障")
            return (
                [poi(f"shard-{i}", name=f"测试{i}汽车充电站", typecode="011100") for i in range(25)]
                if bounds == [112.9, 28.1, 113, 28.2]
                else []
            ), 1

    failed = Provider(True)
    with pytest.raises(CollectionError):
        execute_supplement(collector_db, run_id, failed)
    resumed = Provider()
    execute_supplement(collector_db, run_id, resumed)
    assert resumed.calls[0][1] == 2
    with collector_db() as db:
        run = db.get(CollectionRun, run_id)
        assert run.status == "completed"
        report = supplement_report(db, run)
        assert report["shardCount"] == 5
        assert report["districts"][0]["cappedLeafShards"] == 0
        assert report["districts"][0]["addedCount"] == 25
        assert report["quality"]["rawCount"] == 200
        assert report["quality"]["insertedCount"] == 25
        assert report["quality"]["retainedDuplicateCount"] == 175
        assert report["quality"]["rejectedCount"] == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(CollectionPage)
                .where(CollectionPage.run_id == run_id)
            )
            == 12
        )
    # A subsequent batch must not change this completed batch's reported growth.
    subsequent = new_run(collector_db)
    with collector_db.begin() as db:
        runner.persist_page(
            db, subsequent, SCOPE, "长沙市", 1, [poi("later", name="后续汽车充电站")], 1
        )
        again = supplement_report(db, db.get(CollectionRun, run_id))
        assert again["districts"][0]["afterCount"] == 25
