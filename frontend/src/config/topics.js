export const topics = [
  {
    slug: 'spatial',
    title: '空间格局分析',
    shortTitle: '空间格局',
    eyebrow: 'SPATIAL PATTERN',
    description: '查看真实POI样本的区县分布、样本密度与聚集差异。',
    outputs: ['设施空间分布', '集聚特征', '密度热力分析'],
    input: '充电设施坐标、行政区划边界',
    icon: 'map',
  },
  {
    slug: 'accessibility',
    title: '可达性分析',
    shortTitle: '可达性',
    eyebrow: 'ACCESSIBILITY',
    description: '比较122区县代表点的5/10/15分钟道路观测，定位低可达性代表点。',
    outputs: ['区县代表点道路时间', '5 / 10 / 15分钟阈值比较', '低可达性代表点清单'],
    input: '站点位置、道路网络、出行方式',
    icon: 'time',
  },
  {
    slug: 'differences',
    title: '市州差异分析',
    shortTitle: '市州差异',
    eyebrow: 'REGIONAL COMPARISON',
    description: '对比14市州POI样本数量、样本密度与样本覆盖差异。',
    outputs: ['市州指标对比', '区县分布比较', '样本密度与直线覆盖差异'],
    input: '同一批次POI样本、真实行政边界与空间快照',
    icon: 'bars',
  },
]
export const cityModules = [
  { title: '区县充电设施分布', description: '区县边界与设施分级展示', key: 'district' },
  { title: '网格POI样本密度', description: '网格样本密度与描述性聚集分布', key: 'heat' },
  { title: '1km直线样本覆盖', description: '样本几何缓冲范围与覆盖图层', key: 'coverage' },
  {
    title: '5/10/15分钟可达性',
    description: '区县代表点到候选站点的真实驾车观测',
    key: 'accessibility',
  },
]
