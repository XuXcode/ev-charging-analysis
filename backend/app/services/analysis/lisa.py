"""Global and local spatial autocorrelation (Moran's I / LISA) for the frozen sample grid.

The input is the `layers.grid` FeatureCollection already stored in an analysis
snapshot, so every statistic describes exactly the same 5km cells the map draws.
Nothing here recomputes geometry, re-reads live stations or invents values.

Grid cells are kept only where the province boundary intersects the 5km square,
so the lattice is irregular. Contiguity is therefore rebuilt from the frozen
"x:y" cell index rather than from a regular raster assumption.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter

import numpy as np

LISA_VERSION = "grid-lisa-v1"
# Conditional permutation resolution is 1/(B+1). With 8,895 cells the BH-FDR rank-one
# threshold is alpha/m ~= 5.6e-6, which needs B >= ~178,000 permutations to be reachable.
# 249,999 permutations were measured at >6 minutes per run, so this build reports
# conditionally-significant cells at p<0.05 (GeoDa's default LISA reading) and records
# the FDR result explicitly as *unreachable* rather than presenting "0 significant
# cells" as evidence of no local clustering.
PERMUTATIONS = 9_999
PERMUTATION_SEED = 20261004
FDR_ALPHA = 0.05
QUADRANT_CLASS = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}
CLASS_LABELS = {
    "HH": "高—高聚集",
    "LL": "低—低聚集",
    "HL": "高—低异常",
    "LH": "低—高异常",
    "NS": "不显著",
}


def _cell_key(cell_id: str) -> tuple[int, int]:
    x, y = cell_id.split(":")
    return int(x), int(y)


def build_weights(cell_ids, queen=True):
    """Binary contiguity over the frozen lattice; row-standardised afterwards."""
    from libpysal.weights import W

    index = {_cell_key(cell_id): cell_id for cell_id in cell_ids}
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if queen:
        offsets += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    neighbours, weights = {}, {}
    for (x, y), cell_id in index.items():
        found, row = [], []
        for dx, dy in offsets:
            other = index.get((x + dx, y + dy))
            if other is not None:
                found.append(other)
                row.append(1.0)
        neighbours[cell_id] = found
        weights[cell_id] = row
    weight = W(neighbours, weights, ids=list(cell_ids), silence_warnings=True)
    weight.transform = "r"
    return weight


def benjamini_hochberg(p_values, alpha=FDR_ALPHA):
    """BH step-up procedure returning (rejected, q_values).

    The threshold grows with rank (alpha * k / m), so a cell does not need
    p < alpha/m to be rejected. q values are made monotone from the largest
    p-value downwards, which is the standard adjusted-p definition.
    """
    p = np.asarray(p_values, dtype=float)
    q = np.ones(p.shape, dtype=float)
    valid = np.flatnonzero(np.isfinite(p))
    if not valid.size:
        return np.zeros(p.shape, dtype=bool), q
    order = valid[np.argsort(p[valid])]
    m = order.size
    scaled = p[order] * m / np.arange(1, m + 1)
    scaled = np.minimum.accumulate(scaled[::-1])[::-1]
    q[order] = np.minimum(scaled, 1.0)
    return q <= alpha, q


def _grid_signature(features):
    """Fingerprint the exact grid values the statistics were computed from."""
    payload = [[f["properties"]["id"], f["properties"].get("count")] for f in features]
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def _conclusion(
    global_stats,
    counts,
    zero_share,
    n,
    raw_count=0,
    bonferroni_threshold=None,
    minimum_p=None,
    bonferroni_reachable=True,
):
    signs = (
        "样本密度相近的网格倾向于相邻（正空间自相关）"
        if global_stats["moranI"] > global_stats["expectedI"]
        else "相邻网格的样本密度倾向于相反（负空间自相关）"
    )
    if global_stats["pSim"] < 0.05:
        head = (
            f"全局Moran's I={global_stats['moranI']:.4f}，置换检验p={global_stats['pSim']:.4f}，"
            f"{signs}。"
        )
    else:
        head = (
            f"全局Moran's I={global_stats['moranI']:.4f}，置换检验p={global_stats['pSim']:.4f}，"
            "未通过0.05显著性检验，不能据此声称全省存在稳定空间聚集。"
        )
    significant = sum(counts[key] for key in ("HH", "LL", "HL", "LH"))
    if significant:
        body = (
            f"BH-FDR校正后{significant}个网格局部关联显著"
            f"（未校正p<0.05为{raw_count}个）："
            f"高—高{counts['HH']}个、低—低{counts['LL']}个、"
            f"高—低{counts['HL']}个、低—高{counts['LH']}个。"
        )
    else:
        body = (
            f"BH-FDR校正后没有网格通过局部显著性检验（未校正p<0.05为{raw_count}个），"
            "不能据此判定局部聚集存在。"
        )
    if not bonferroni_reachable and bonferroni_threshold and minimum_p:
        body += (
            f"Bonferroni阈值{bonferroni_threshold:.1e}低于本次置换的p值下限{minimum_p:.0e}，"
            "故未采用Bonferroni口径。"
        )
    tail = (
        f'{n}个网格中{zero_share:.1f}%为零样本，统计量主要刻画样本"有/无"的空间分布，'
        "不能解释为真实充电需求或设施不足。"
    )
    return head + body + tail


def lisa_analysis(
    grid,
    *,
    variable="density",
    queen=True,
    permutations=PERMUTATIONS,
    seed=PERMUTATION_SEED,
    alpha=FDR_ALPHA,
):
    """Return (items, metadata) for one frozen grid layer."""
    from esda.moran import Moran, Moran_Local

    started = time.perf_counter()
    features = grid.get("features") or []
    if len(features) < 30:
        raise ValueError("网格数量不足以进行空间自相关分析")
    ids = [str(feature["properties"]["id"]) for feature in features]
    if len(set(ids)) != len(ids):
        raise ValueError("网格编号重复，无法构造邻接关系")

    values = np.asarray(
        [float(feature["properties"].get(variable) or 0.0) for feature in features], dtype=float
    )
    if not np.isfinite(values).all():
        raise ValueError("网格指标含非有限值，停止LISA计算")
    if float(np.ptp(values)) == 0.0:
        raise ValueError("网格指标无变异，无法计算Moran's I")

    weight = build_weights(ids, queen=queen)
    cardinalities = np.asarray([weight.cardinalities[cell_id] for cell_id in ids], dtype=int)
    islands = int((cardinalities == 0).sum())
    if islands:
        raise ValueError(f"{islands}个网格没有邻接单元，需先修复网格邻接再计算")

    # esda 2.10's global Moran has no seed argument; pin the legacy NumPy global
    # generator so the permutation p-value is reproducible for the same build.
    np.random.seed(seed)
    global_moran = Moran(values, weight, permutations=permutations)
    local = Moran_Local(
        values, weight, permutations=permutations, seed=seed, keep_simulations=False
    )

    p_sim = np.asarray(local.p_sim, dtype=float)
    p_sim = np.where(np.isfinite(p_sim), p_sim, 1.0)
    p_fdr, q_fdr = benjamini_hochberg(p_sim, alpha)
    raw_significant = p_sim < alpha
    # BH is a step-up procedure: it can still reject hypotheses when the permutation
    # floor (1/(B+1)) exceeds alpha/m, because the threshold grows with rank. The map
    # and the panel therefore use the FDR decision as the primary LISA class.
    significant = p_fdr
    quadrants = np.asarray(local.q, dtype=int)
    local_i = np.asarray(local.Is, dtype=float)

    counts = Counter()
    items = []
    for index, cell_id in enumerate(ids):
        quadrant = int(quadrants[index])
        passed = bool(significant[index])
        label = QUADRANT_CLASS.get(quadrant, "NS") if passed else "NS"
        counts[label] += 1
        items.append(
            {
                "id": cell_id,
                "class": label,
                "classLabel": CLASS_LABELS[label],
                "quadrant": quadrant,
                "localI": round(float(local_i[index]), 6) if np.isfinite(local_i[index]) else None,
                "pSim": round(float(p_sim[index]), 6),
                "qFdr": round(float(q_fdr[index]), 6),
                "significant": passed,
                "rawSignificant": bool(raw_significant[index]),
                "count": features[index]["properties"].get("count"),
                "density": features[index]["properties"].get("density"),
                "areaKm2": features[index]["properties"].get("areaKm2"),
            }
        )

    positive = int((values > 0).sum())
    zero_share = (len(values) - positive) / len(values) * 100
    areas = [float(feature["properties"].get("areaKm2") or 0.0) for feature in features]
    edge_cells = sum(1 for area in areas if area < 24.9)
    edge_samples = sum(
        int(feature["properties"].get("count") or 0)
        for feature in features
        if float(feature["properties"].get("areaKm2") or 0.0) < 24.9
    )
    global_stats = {
        "moranI": float(global_moran.I),
        "expectedI": float(global_moran.EI),
        "variance": float(global_moran.VI_norm),
        "zScore": float(global_moran.z_norm),
        "pSim": float(global_moran.p_sim),
        "pNormal": float(global_moran.p_norm),
    }
    metadata = {
        "version": LISA_VERSION,
        "variable": variable,
        "variableLabel": "POI样本密度" if variable == "density" else variable,
        "unit": "条/km²" if variable == "density" else None,
        "cellCount": len(ids),
        "positiveCellCount": positive,
        "zeroSampleCells": len(ids) - positive,
        "zeroSharePercent": round(zero_share, 2),
        "edgeCellCount": edge_cells,
        "edgeSampleCount": edge_samples,
        "weights": {
            "type": "queen" if queen else "rook",
            "transform": "r",
            "meanNeighbors": round(float(cardinalities.mean()), 3),
            "minNeighbors": int(cardinalities.min()),
            "maxNeighbors": int(cardinalities.max()),
            "islandCount": islands,
        },
        "permutations": permutations,
        "seed": seed,
        "alpha": alpha,
        "multipleTesting": "Benjamini-Hochberg FDR（alpha=0.05）",
        "minimumReachableP": round(1 / (permutations + 1), 8),
        "rawSignificantCount": int(raw_significant.sum()),
        "fdrSignificantCount": int(p_fdr.sum()),
        "bonferroniThreshold": round(alpha / len(ids), 10),
        "bonferroniReachable": (1 / (permutations + 1)) <= alpha / len(ids),
        "global": global_stats,
        "classCounts": {key: counts.get(key, 0) for key in ("HH", "LL", "HL", "LH", "NS")},
        "significantCount": sum(counts.get(key, 0) for key in ("HH", "LL", "HL", "LH")),
        "sourceGridHash": _grid_signature(features),
        "computedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds": round(time.perf_counter() - started, 3),
        "caveats": [
            "输入为分析快照中冻结的5km裁切网格，未重算几何或读取实时站点。",
            f"边缘网格按实际裁切面积计算密度：面积小于24.9km²的网格{edge_cells}个，"
            f"其中{edge_samples}条样本落在此类网格，可能放大局部密度。",
            f"{len(ids) - positive}个网格（{zero_share:.1f}%）为零样本，"
            '高值聚集主要反映样本"有/无"的空间分布，不代表真实充电需求。',
            f"置换检验{permutations}次（固定随机种子可复现）；"
            "局部显著性采用Benjamini-Hochberg FDR校正（alpha=0.05）。",
        ],
    }
    metadata["summary"] = (
        f"全局Moran's I={global_stats['moranI']:.4f}"
        f"（置换p={global_stats['pSim']:.4f}，"
        f"{'显著' if global_stats['pSim'] < 0.05 else '不显著'}"
        f"{'正' if global_stats['moranI'] > global_stats['expectedI'] else '负'}空间自相关）；"
        f"FDR校正后{metadata['significantCount']}个网格显著，"
        f"未校正p<0.05为{metadata['rawSignificantCount']}个。"
    )
    metadata["conclusion"] = _conclusion(
        global_stats,
        counts,
        zero_share,
        len(ids),
        raw_count=metadata["rawSignificantCount"],
        bonferroni_threshold=metadata["bonferroniThreshold"],
        minimum_p=metadata["minimumReachableP"],
        bonferroni_reachable=metadata["bonferroniReachable"],
    )
    return items, metadata


def _default_snapshot_id(session):
    from sqlalchemy import func, select

    from app.models.analysis import AnalysisSnapshot

    return session.scalar(
        select(AnalysisSnapshot.id)
        .where(AnalysisSnapshot.status == "completed")
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["classification"].as_string(), "")
            == ""
        )
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["reviewStatus"].as_string(), "")
            == ""
        )
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["needsReview"].as_string(), "")
            == ""
        )
        .where(func.coalesce(AnalysisSnapshot.parameters["filters"]["batch"].as_string(), "") == "")
        .order_by(AnalysisSnapshot.computed_at.desc())
        .limit(1)
    )


def _latest_per_filter(session):
    """One snapshot per filter set, newest first, so every selectable layer resolves."""
    from sqlalchemy import select

    from app.models.analysis import AnalysisSnapshot

    rows = session.execute(
        select(AnalysisSnapshot.id, AnalysisSnapshot.parameters)
        .where(AnalysisSnapshot.status == "completed")
        .order_by(AnalysisSnapshot.computed_at.desc())
    ).all()
    seen, picked = set(), []
    for snapshot_id, parameters in rows:
        filters = (parameters or {}).get("filters") or {}
        key = (
            filters.get("classification"),
            filters.get("reviewStatus"),
            filters.get("needsReview"),
            filters.get("batch"),
        )
        if key in seen:
            continue
        seen.add(key)
        picked.append(snapshot_id)
    return picked


def main():
    """Backfill LISA onto existing snapshots without recomputing geometry."""
    import argparse
    import json

    from sqlalchemy.orm.attributes import flag_modified

    from app.core.config import Settings
    from app.db.session import create_db_engine, create_session_factory
    from app.models.analysis import AnalysisSnapshot

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="快照ID；默认当前默认筛选的最新完成快照")
    parser.add_argument("--all", action="store_true", help="为每个筛选口径的最新完成快照补算")
    parser.add_argument("--force", action="store_true", help="覆盖快照中已有的LISA层")
    parser.add_argument("--dry-run", action="store_true", help="只计算并打印，不写回快照")
    args = parser.parse_args()

    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            if args.all:
                summary = []
                for snapshot_id in _latest_per_filter(session):
                    snapshot = session.get(AnalysisSnapshot, snapshot_id)
                    if snapshot is None or snapshot.status != "completed":
                        continue
                    if "lisa" in (snapshot.result.get("layers") or {}) and not args.force:
                        summary.append({"snapshotId": snapshot_id, "status": "skipped"})
                        continue
                    try:
                        items, metadata = lisa_analysis(snapshot.result["layers"]["grid"])
                    except ValueError as failure:
                        # No variance (for example a zero-sample filter): record the
                        # reason so the API can explain it instead of returning empty.
                        snapshot.result.setdefault("layers", {})["lisa"] = {
                            "type": "LISAProperties",
                            "items": [],
                        }
                        snapshot.result.setdefault("metadata", {})["lisa"] = {
                            "version": LISA_VERSION,
                            "error": str(failure),
                        }
                        flag_modified(snapshot, "result")
                        session.commit()
                        summary.append(
                            {"snapshotId": snapshot_id, "status": "error", "reason": str(failure)}
                        )
                        continue
                    snapshot.result["layers"]["lisa"] = {
                        "type": "LISAProperties",
                        "items": items,
                    }
                    snapshot.result["metadata"]["lisa"] = metadata
                    flag_modified(snapshot, "result")
                    session.commit()
                    summary.append(
                        {
                            "snapshotId": snapshot_id,
                            "status": "ok",
                            "stationCount": snapshot.result["metadata"].get("stationCount"),
                            "moranI": round(metadata["global"]["moranI"], 4),
                            "fdr": metadata["fdrSignificantCount"],
                        }
                    )
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            snapshot_id = args.snapshot or _default_snapshot_id(session)
            if not snapshot_id:
                raise SystemExit("没有已完成的分析快照")
            snapshot = session.get(AnalysisSnapshot, snapshot_id)
            if snapshot is None or snapshot.status != "completed":
                raise SystemExit("快照不存在或未完成")
            if "lisa" in (snapshot.result.get("layers") or {}) and not args.force:
                raise SystemExit("该快照已有LISA层；如需重算请加 --force")
            items, metadata = lisa_analysis(snapshot.result["layers"]["grid"])
            output = {**metadata, "snapshotId": snapshot_id}
            if args.dry_run:
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return
            snapshot.result["layers"]["lisa"] = {"type": "LISAProperties", "items": items}
            snapshot.result["metadata"]["lisa"] = metadata
            flag_modified(snapshot, "result")
            session.commit()
            print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
