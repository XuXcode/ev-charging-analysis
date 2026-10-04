"""Presentation contracts, not spatial-analysis algorithms."""

INDICATORS = [
    {
        "key": "stations",
        "label": "充电站",
        "unit": "座",
        "precision": 0,
        "description": "统计期末充电站存量，按快照展示；地图站点列表不是统计总量。",
    },
    {
        "key": "piles",
        "label": "公共充电桩",
        "unit": "个",
        "precision": 0,
        "description": "统计期末对外开放的充电桩存量，不含私人自用桩。",
    },
    {
        "key": "density",
        "label": "设施密度",
        "unit": "座/100km²",
        "precision": 2,
        "description": "充电站存量 ÷ 已核验的统计面积 × 100；面积或存量缺失时暂无数据。高德搜索条目不用于推算区域密度。",
    },
]
GROUP_DEFINITIONS = [
    {
        "key": "region",
        "label": "区域统计",
        "description": "按行政区展示分组汇总；完整设施统计接入前不计算数量占比。",
    },
    {
        "key": "scale",
        "label": "市州分组",
        "description": "按站点存量分组：≥1,000座、500–999座、<500座。",
    },
]
RESERVED_CHARTS = [
    {"key": "comparison", "label": "市州对比"},
    {
        "key": "scatter",
        "label": "密度散点",
        "title": "设施规模与密度",
        "description": "后续展示市州充电站数量与设施密度的关系。",
        "required": "市州指标与散点图数据",
    },
    {
        "key": "quadrant",
        "label": "供需四象限",
        "title": "供需匹配分布",
        "description": "后续展示统一口径下的供给与需求指标。",
        "required": "供给指数、需求指数与划分阈值",
    },
    {
        "key": "accessibility",
        "label": "可达性分布",
        "title": "出行时间与服务范围",
        "description": "后续展示5、10、15分钟范围内的服务分布。",
        "required": "后端可达性分析结果",
    },
]
