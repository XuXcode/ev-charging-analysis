// API-shaped demonstration metadata; replace together with GET /dashboard.
export const indicatorDefinitions = [
  {
    key: 'stations',
    label: '充电站',
    unit: '座',
    precision: 0,
    description: '统计期末充电站存量。示例站点仅用于地图交互，不等于完整站点清单。',
  },
  {
    key: 'piles',
    label: '公共充电桩',
    unit: '个',
    precision: 0,
    description: '统计期末对外开放的充电桩存量，不含私人自用桩。',
  },
  {
    key: 'density',
    label: '设施密度',
    unit: '座/100km²',
    precision: 2,
    description: '充电站数量 ÷ 统计面积 × 100；面积与数量均为模拟值，不是建成区或人口密度。',
  },
]
export const groupDefinitions = [
  {
    key: 'region',
    label: '区域统计',
    description: '按展示区域汇总，各组互不重叠，覆盖14市州；不作为正式统计分区。',
  },
  {
    key: 'scale',
    label: '市州分组',
    description: '按模拟充电站存量分组：≥1,000座、500–999座、<500座。分组仅用于交互展示。',
  },
]
export const reservedCharts = [
  { key: 'comparison', label: '市州对比' },
  {
    key: 'scatter',
    label: '密度散点',
    title: '设施规模与密度',
    description: '后续展示市州充电站数量与设施密度的关系。',
    required: '市州指标与散点图数据',
  },
  {
    key: 'quadrant',
    label: '供需四象限',
    title: '供需匹配分布',
    description: '后续展示统一口径下的供给与需求指标。',
    required: '供给指数、需求指数与划分阈值',
  },
  {
    key: 'accessibility',
    label: '可达性分布',
    title: '出行时间与服务范围',
    description: '后续展示5、10、15分钟范围内的服务分布。',
    required: '后端可达性分析结果',
  },
]
