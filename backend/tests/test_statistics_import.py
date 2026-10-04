import csv
import json
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import PublicStatistic
from app.services.statistics_import import FIELDS, import_statistics, validate_record


def record(**overrides):
    # Test-only values; never loaded into the application database or displayed as data.
    return {
        "region_adcode": "430100",
        "year": 2024,
        "metric": "public_pile_count",
        "value": 10,
        "unit": "个",
        "source_name": "单元测试来源",
        "source_url": "https://example.org/test-source",
        "source_kind": "public",
        "scope_description": "单元测试，不是正式统计",
        **overrides,
    }


def write_file(tmp_path, rows, suffix=".json"):
    path = tmp_path / ("test-statistics" + suffix)
    if suffix == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=sorted(FIELDS))
            writer.writeheader()
            writer.writerows(rows)
    return path


@pytest.mark.parametrize("suffix", [".json", ".csv"])
def test_import_provenance_and_idempotency(demo_session, tmp_path, suffix):
    path = write_file(tmp_path, [record(), record()], suffix)
    result = import_statistics(demo_session, path)
    assert result["inserted"] == 1 and result["duplicates"] == 1
    again = import_statistics(demo_session, path)
    assert again["inserted"] == 0 and again["duplicates"] == 2
    saved = demo_session.scalar(select(PublicStatistic))
    assert saved.value == Decimal(10)
    assert saved.source_name == "单元测试来源"
    assert saved.year == 2024 and saved.scope_description == "单元测试，不是正式统计"
    assert saved.file_sha256 == result["fileSha256"] and saved.row_number == 1


def test_invalid_batch_is_atomic(demo_session, tmp_path):
    path = write_file(tmp_path, [record(), record(value="NaN")])
    with pytest.raises(ValueError, match="记录2"):
        import_statistics(demo_session, path)
    assert demo_session.scalar(select(func.count()).select_from(PublicStatistic)) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"value": "Infinity"},
        {"value": -1},
        {"value": 1.5},
        {"value": True},
        {"value": "1e14"},
        {"region_adcode": "430999"},
        {"region_adcode": "110000"},
        {"year": 9999},
        {"year": "2024.5"},
        {"metric": "unknown"},
        {"unit": "辆"},
        {"source_name": ""},
        {"scope_description": ""},
        {"source_kind": "amap"},
        {"source_url": "file:///secret"},
        {"source_url": "https://user:pass@example.org"},
    ],
)
def test_reject_unreliable_or_invalid_fields(overrides):
    with pytest.raises(ValueError):
        validate_record(record(**overrides), {"430100"})


def test_zero_is_valid_only_when_explicit_and_sourced():
    assert validate_record(record(value=0), {"430100"})["value"] == 0
    with pytest.raises(ValueError):
        validate_record(record(value=None), {"430100"})


def test_sources_with_distinct_scopes_are_not_merged(demo_session, tmp_path):
    path = write_file(tmp_path, [record(), record(scope_description="另一测试口径")])
    assert import_statistics(demo_session, path)["inserted"] == 2


def test_read_api_retains_provenance_and_missing_statistics(client, demo_session, tmp_path):
    assert client.get("/api/v1/statistics/public").json()["data"]["total"] == 0
    import_statistics(demo_session, write_file(tmp_path, [record()]))
    data = client.get(
        "/api/v1/statistics/public", params={"adcode": "430100", "year": 2024}
    ).json()["data"]
    assert data["total"] == 1 and data["items"][0]["value"] == 10
    assert data["items"][0]["sourceUrl"] == "https://example.org/test-source"
    assert data["items"][0]["scopeDescription"] == "单元测试，不是正式统计"
    assert (
        client.get("/api/v1/statistics/public", params={"year": 2023}).json()["data"]["total"] == 0
    )
    assert client.get("/api/v1/statistics/public", params={"page_size": 101}).status_code == 422


def test_official_import_is_separate_and_rejects_public_claims(client, demo_session, tmp_path):
    from app.models import OfficialStatistic

    path = write_file(
        tmp_path, [record(source_kind="official", metric="charging_gun_count", unit="把")]
    )
    result = import_statistics(demo_session, path, official=True)
    assert result["table"] == "official_statistics"
    assert result["inserted"] == 1
    assert import_statistics(demo_session, path, official=True)["duplicates"] == 1
    saved = demo_session.scalar(select(OfficialStatistic))
    assert saved.updated_at and saved.file_sha256 == result["fileSha256"]
    assert demo_session.scalar(select(func.count()).select_from(PublicStatistic)) == 0
    data = client.get("/api/v1/statistics/official").json()["data"]
    assert data["items"][0]["unit"] == "把"
    assert data["items"][0]["updatedAt"].endswith("Z")
    assert client.get("/api/v1/statistics/public").json()["data"]["total"] == 0
    with pytest.raises(ValueError, match="source_kind=official"):
        import_statistics(demo_session, write_file(tmp_path, [record()]), official=True)
