"""Offline replay consumes frozen evidence, not current POIs or provider routes."""

import argparse
import json

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import PlanningRun
from app.services.analysis.optimization import VERSION, greedy, mclp
from app.services.analysis.road import frozen_digest


def replay(session, run_id):
    row = session.get(PlanningRun, run_id)
    if row is None:
        raise ValueError("方案不存在")
    if row.algorithm_version != VERSION or row.input_hash != frozen_digest(row.inputs):
        raise ValueError("冻结输入或算法版本不匹配，拒绝重放")
    algorithm = row.parameters["algorithm"]
    result = (
        greedy(row.inputs["problem"])
        if algorithm == "greedy"
        else mclp(row.inputs["problem"], time_limit=row.parameters["timeLimitSeconds"])
    )
    keys = ["selectedIds", "before", "after", "coverageGain", "newlyCoveredIds", "uncoveredIds"]
    differences = [key for key in keys if result[key] != row.result[key]]
    return {
        "runId": run_id,
        "inputHash": row.input_hash,
        "algorithmVersion": VERSION,
        "equal": not differences,
        "differentFields": differences,
        "apiCalls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description="仅离线重放冻结选址方案，不调用高德")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            print(json.dumps(replay(session, args.run_id), ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
