"""Prepare reusable category/review scopes offline; API readers never run geometry."""

import json
from typing import get_args

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.schemas.filters import PoiClassification, ReviewStatus
from app.services.analysis.job import run_analysis


def main():
    engine = create_db_engine(Settings())
    try:
        for classification, review_status, needs_review in (
            (classification, review_status, needs_review)
            for classification in (None, *get_args(PoiClassification))
            for review_status in (None, *get_args(ReviewStatus))
            for needs_review in (None, True)
        ):
            with create_session_factory(engine)() as session, session.begin():
                result = run_analysis(
                    session,
                    classification=classification,
                    review_status=review_status,
                    needs_review=needs_review,
                )
            print(
                json.dumps(
                    {
                        "classification": classification,
                        "reviewStatus": review_status,
                        "needsReview": needs_review,
                        "snapshotId": result["snapshotId"],
                        "reused": result["reused"],
                        "count": result.get("province", {}).get("count"),
                        "seconds": round(result["seconds"], 3),
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
