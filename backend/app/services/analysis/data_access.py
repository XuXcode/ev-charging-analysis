"""未来分析任务复用现有仓储，不通过 HTTP 抓取自己的数据。"""

from app.repositories.data import RegionRepository, SnapshotRepository, StationRepository

__all__ = ["RegionRepository", "SnapshotRepository", "StationRepository"]
