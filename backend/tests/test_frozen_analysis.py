from collections import namedtuple
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.analysis.job import digest, freeze_inputs, station_fingerprint, thaw_inputs


def test_frozen_inputs_preserve_coordinates_timestamps_flags_and_source_boundary():
    record = namedtuple(
        "Station",
        "id poi_id adcode longitude latitude collected_at classification needs_review review_status rules_version quality_run_id",
    )
    row = record(
        7,
        "original-poi",
        "430102",
        Decimal("112.990001"),
        Decimal("28.190001"),
        datetime(2026, 10, 3, 8, 1, 2, 123456),
        "unknown",
        True,
        "unreviewed",
        "v1",
        "a" * 32,
    )
    boundary = SimpleNamespace(
        adcode="430102",
        city_code="430100",
        name="边界测试",
        level="district",
        geometry={"type": "Polygon", "coordinates": [[[112, 28], [113, 28], [113, 29], [112, 28]]]},
        content_hash="h",
        source_url="https://example.org/boundary",
        coordinate_system="GCJ-02",
        fetched_at=datetime(2026, 10, 3),
    )
    scope = SimpleNamespace(
        adcode="430102", city_code="430100", name="测试", run_id="a" * 32, completeness_warning=True
    )
    frozen = freeze_inputs(
        SimpleNamespace(id="a" * 32), [boundary], [scope], [row], {"radiusM": 1000}
    )
    original_hash = digest(frozen)
    # Subsequent source geometry mutation cannot mutate already frozen evidence.
    # JSON serialization simulates the actual snapshot column persistence boundary.
    import json

    frozen = json.loads(json.dumps(frozen))
    boundary.geometry["coordinates"][0][0][0] = 114
    run, boundaries, scopes, rows = thaw_inputs(frozen)
    assert run.id == "a" * 32
    assert station_fingerprint(rows) == station_fingerprint([row])
    assert rows[0].collected_at.microsecond == 123456
    assert scopes[0].completeness_warning
    assert boundaries[0].geometry["coordinates"][0][0][0] == 112
    assert digest(frozen) == original_hash
