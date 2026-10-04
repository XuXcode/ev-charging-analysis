from types import SimpleNamespace

import pytest
from shapely.geometry import box
from sqlalchemy import func, select

from app.models import AnalysisBoundary, BoundaryRevision
from app.services.analysis.geometry import to_metric
from app.services.boundary_review import assignment, install, preserve_revision


def test_assignment_distinguishes_wrong_code_outside_and_shared_boundary():
    geometries = {
        "430102": to_metric(box(113, 28, 113.01, 28.01)),
        "430103": to_metric(box(113.01, 28, 113.02, 28.01)),
    }
    rows = [
        SimpleNamespace(id=1, poi_id="wrong", adcode="430103", longitude=113.005, latitude=28.005),
        SimpleNamespace(id=2, poi_id="outside", adcode="430102", longitude=112, latitude=28),
        SimpleNamespace(id=3, poi_id="edge", adcode="430102", longitude=113.01, latitude=28),
    ]
    result = assignment(rows, geometries)
    assert result["mismatch"] == 2
    assert result["outside"] == 1
    assert result["ambiguous"] == 1
    assert result["records"][0]["geometryAdcodes"] == ["430102"]


def test_partial_boundary_replacement_is_rejected_without_writes(session):
    before = session.scalar(select(func.count()).select_from(BoundaryRevision))
    with pytest.raises(ValueError, match="122"):
        install(session, {"records": {}}, apply=True)
    assert session.scalar(select(func.count()).select_from(BoundaryRevision)) == before


def test_revision_retains_predecessor_and_is_idempotent(session):
    from app.models.entities import utc_now

    original = {"type": "Polygon", "coordinates": [[[113, 28], [114, 28], [114, 29], [113, 28]]]}
    row = AnalysisBoundary(
        adcode="430102",
        city_code="430100",
        name="测试区",
        level="district",
        geometry=original,
        source_url="https://example.org/old",
        coordinate_system="GCJ-02",
        content_hash="a" * 64,
        fetched_at=utc_now(),
    )
    preserve_revision(session, row, "before change")
    session.flush()
    preserve_revision(session, row, "same version")
    session.flush()
    versions = list(
        session.scalars(select(BoundaryRevision).where(BoundaryRevision.adcode == row.adcode))
    )
    assert len(versions) == 1
    row.geometry = {"type": "Polygon", "coordinates": []}
    row.content_hash = "b" * 64
    assert versions[0].geometry == original
    assert versions[0].content_hash == "a" * 64
