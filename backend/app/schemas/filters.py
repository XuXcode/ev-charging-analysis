"""Shared validated vocabulary for station, quality and analysis scope filters."""

from typing import Literal

PoiClassification = Literal[
    "public_candidate", "dedicated", "personal", "suspected_closed", "unknown"
]
ReviewStatus = Literal["unreviewed", "confirmed", "needs_review"]
