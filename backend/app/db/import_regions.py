"""Import map metadata only, never charging-facility counts or estimated areas."""

import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models import Region


def import_regions(session):
    data = json.loads((Path(__file__).parent / "fixtures/regions.json").read_text(encoding="utf-8"))
    for record in data["regions"]:
        row = session.scalar(select(Region).where(Region.adcode == record["adcode"]))
        if row is None:
            row = Region(**record)
            session.add(row)
        elif row.is_demo:
            raise ValueError("存在模拟行政区；请使用独立的空数据库导入真实边界元信息")
        session.flush()
    return len(data["regions"])


def main():
    engine = create_db_engine(get_settings())
    try:
        with create_session_factory(engine).begin() as session:
            count = import_regions(session)
        print(f"行政区展示元信息导入完成：{count}个（含湖南省）；未导入业务统计。")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
