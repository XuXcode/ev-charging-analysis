"""Atomic CSV/JSON import, with provenance; no collection or extrapolation."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisBoundary, OfficialStatistic, PublicStatistic, Region

METRICS = {
    "pile_count": ("充电桩统计数量", "个"),
    "charging_gun_count": ("充电枪统计数量", "把"),
    "public_charging_gun_count": ("公共充电枪统计数量", "把"),
    "station_count": ("充电站统计数量", "座"),
    "public_pile_count": ("公共充电桩统计数量", "个"),
    "dc_pile_count": ("直流充电桩统计数量", "个"),
    "ac_pile_count": ("交流充电桩统计数量", "个"),
    "new_energy_vehicle_count": ("新能源汽车保有量", "辆"),
    "vehicle_count": ("汽车保有量", "辆"),
    "population": ("人口统计数量", "人"),
}
FIELDS = {
    "region_adcode",
    "year",
    "metric",
    "value",
    "unit",
    "source_name",
    "source_url",
    "source_kind",
    "scope_description",
}


def read_statistics(path: Path) -> tuple[list[dict], str]:
    if path.suffix.lower() not in {".csv", ".json"}:
        raise ValueError("仅支持 UTF-8 CSV 或 JSON 文件")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("导入文件不得超过10MB")
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if set(reader.fieldnames or []) != FIELDS or len(reader.fieldnames or []) != len(FIELDS):
            raise ValueError("CSV表头必须与统计导入模板一致")
        rows = list(reader)
    else:
        rows = json.loads(text)
    if not isinstance(rows, list) or len(rows) > 100000:
        raise ValueError("JSON须为记录数组，单批最多100000行")
    return rows, hashlib.sha256(raw).hexdigest()


def validate_record(row: dict, allowed_codes: set[str]) -> dict:
    if not isinstance(row, dict) or set(row) != FIELDS:
        raise ValueError("统计记录字段不符合导入模板")
    if any(isinstance(v, (bool, list, dict)) or v is None for v in row.values()):
        raise ValueError("字段不得为空或使用布尔/复合类型")
    data = {key: str(value).strip() for key, value in row.items()}
    if any(not value for value in data.values()):
        raise ValueError("所有字段必填；缺失统计应省略记录，不填写零")
    if (
        not re.fullmatch(r"43\d{4}", data["region_adcode"])
        or data["region_adcode"] not in allowed_codes
    ):
        raise ValueError("行政编码不属于当前湖南省、市州或区县")
    if not re.fullmatch(r"\d{4}", data["year"]):
        raise ValueError("年份须为四位整数")
    year = int(data["year"])
    if not 1900 <= year <= datetime.now().year:
        raise ValueError("年份必须介于1900和当前年份之间")
    if data["metric"] not in METRICS or data["unit"] != METRICS[data["metric"]][1]:
        raise ValueError("指标或单位不符合统计字典")
    try:
        value = Decimal(data["value"])
    except InvalidOperation:
        raise ValueError("统计值必须为数字") from None
    if (
        not value.is_finite()
        or value < 0
        or value != value.to_integral_value()
        or value >= Decimal("1e14")
    ):
        raise ValueError("数量指标必须为非负有限整数，且小于10^14")
    if data["source_kind"] not in {"official", "public"}:
        raise ValueError("来源类别须为official或public")
    parsed = urlparse(data["source_url"])
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("来源链接须为公开HTTP(S)地址，不得包含登录凭据")
    for key, limit in {"source_name": 200, "source_url": 1000, "scope_description": 1000}.items():
        if len(data[key]) > limit:
            raise ValueError(f"{key}超出长度限制")
    data["year"] = year
    data["value"] = value.quantize(Decimal("1"))
    return data


def import_statistics(session, path: Path, *, official: bool = False) -> dict:
    rows, file_hash = read_statistics(path)
    allowed = set(session.scalars(select(Region.adcode))) | set(
        session.scalars(select(AnalysisBoundary.adcode))
    )
    validated = []
    # Validate every row before any write, so failures cannot leave partial imports.
    for number, row in enumerate(rows, 1):
        try:
            validated.append((number, validate_record(row, allowed)))
            if official and validated[-1][1]["source_kind"] != "official":
                raise ValueError("官方统计导入仅接受source_kind=official，需人工核对发布机构及原文")
        except ValueError as error:
            raise ValueError(f"记录{number}：{error}") from None
    model = OfficialStatistic if official else PublicStatistic
    hashes = set(session.scalars(select(model.record_hash)))
    inserted = 0
    for number, data in validated:
        normalized = {**data, "value": str(data["value"])}
        record_hash = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if record_hash in hashes:
            continue
        session.add(
            model(
                **data,
                file_name=path.name,
                file_sha256=file_hash,
                row_number=number,
                record_hash=record_hash,
            )
        )
        hashes.add(record_hash)
        inserted += 1
    session.flush()
    return {
        "table": model.__tablename__,
        "file": path.name,
        "fileSha256": file_hash,
        "rows": len(rows),
        "inserted": inserted,
        "duplicates": len(rows) - inserted,
    }


def main():
    parser = argparse.ArgumentParser(description="导入有来源、年份和口径的湖南公开统计")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--official", action="store_true", help="独立官方统计表；须人工核验原文")
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session, session.begin():
            result = import_statistics(session, args.file, official=args.official)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, f"统计导入失败：{error}\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
