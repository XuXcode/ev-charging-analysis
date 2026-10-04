"""Synthetic fixed inputs are unit tests only, never seeded into business storage."""

import pytest
from shapely.geometry import box, mapping

from app.services.analysis.candidates import filter_candidates, score_candidates
from app.services.analysis.demand import prepare
from app.services.analysis.optimization import greedy, mclp


def fixture_problem():
    cover = {"a": {"1", "2", "3"}, "b": {"1", "2", "4"}, "c": {"3", "5", "6"}}
    return {
        "origins": [{"id": str(i), "weight": 1} for i in range(1, 7)],
        "candidates": [{"id": k} for k in cover],
        "n": 2,
        "metric": "durationSeconds",
        "threshold": 600,
        "baselineCovered": [],
        "edges": [
            {
                "originId": str(i),
                "destinationId": k,
                "status": "ok",
                "durationSeconds": 60 if str(i) in points else 1200,
            }
            for k, points in cover.items()
            for i in range(1, 7)
        ],
    }


def test_greedy_and_mclp_fixed_input_reproduction_and_optimality():
    problem = fixture_problem()
    heuristic = greedy(problem)
    exact = mclp(problem)
    assert heuristic["selectedIds"] == ["a", "c"]
    assert heuristic["coverageGain"] == 5
    assert exact["selectedIds"] == ["b", "c"]
    assert exact["coverageGain"] == 6
    assert exact["solver"]["optimal"]
    assert exact == mclp(problem)
    problem["origins"].reverse()
    problem["candidates"].reverse()
    assert heuristic == greedy(problem)
    assert exact == mclp(problem)


def test_existing_coverage_is_not_counted_as_new_gain_and_budget_is_upper_bound():
    problem = fixture_problem()
    problem["baselineCovered"] = [str(i) for i in range(1, 7)]
    assert greedy(problem)["selectedIds"] == []
    assert mclp(problem)["coverageGain"] == 0
    problem["n"] = 0
    assert greedy(problem)["after"] == greedy(problem)["before"]


def test_missing_od_unknown_weights_and_fake_time_exclusions_are_rejected():
    problem = fixture_problem()
    problem["edges"][0]["status"] = "missing"
    with pytest.raises(ValueError, match="未完整"):
        greedy(problem)
    problem["edges"][0]["status"] = "spatially_excluded"
    with pytest.raises(ValueError, match="空间排除"):
        mclp(problem)
    problem["origins"][0]["weight"] = None
    with pytest.raises(ValueError, match="真实需求"):
        greedy(problem)


def test_demand_missing_constant_and_zero_are_distinct():
    data = prepare(
        [
            {"id": "1", "variables": {"population": 0}},
            {"id": "2", "variables": {"population": 100}},
            {"id": "3", "variables": {}},
        ],
        {"population": 1},
    )
    assert data["nodes"][0]["weight"] == 0
    assert data["nodes"][1]["weight"] == 1
    assert data["nodes"][2]["weight"] is None
    constant = prepare([{"id": "1", "variables": {"parking": 3}}], {"parking": 1})
    assert constant["nodes"][0]["weight"] is None
    assert constant["nodes"][0]["constantVariables"] == ["parking"]


def test_candidates_keep_real_locations_and_trace_exclusions():
    rows = [
        {
            "id": "a",
            "source": "real-fixture",
            "poiId": "1",
            "category": "parking",
            "position": [113, 28],
        },
        {
            "id": "b",
            "source": "real-fixture",
            "poiId": "1",
            "category": "parking",
            "position": [113, 28],
        },
        {
            "id": "c",
            "source": "real-fixture",
            "poiId": "2",
            "category": "office",
            "position": [115, 28],
        },
    ]
    result = filter_candidates(rows, mapping(box(112, 27, 114, 29)), [])
    assert [r["id"] for r in result["candidates"]] == ["a"]
    assert result["candidates"][0]["position"] == rows[0]["position"]
    assert result["excluded"] == [
        {"id": "b", "reason": "duplicate_facility"},
        {"id": "c", "reason": "outside_boundary"},
    ]


def test_candidate_score_requires_sourced_measurements_and_preserves_missing():
    candidates = [{"id": "a"}, {"id": "b"}]
    evidence = {
        "a": {
            "demand": {"value": 0.8, "source": "TEST ONLY", "sourceUrl": "https://example.org/test"}
        }
    }
    result = score_candidates(candidates, evidence, {"demand": 1})
    assert result[0]["score"] == 0.8
    assert result[1]["score"] is None
    assert result[1]["missingScoreVariables"] == ["demand"]
    evidence["a"]["demand"]["sourceUrl"] = ""
    with pytest.raises(ValueError, match="证据"):
        score_candidates(candidates, evidence, {"demand": 1})
