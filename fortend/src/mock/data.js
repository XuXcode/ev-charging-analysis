// SIMULATED DATA ONLY. Figures, areas, station locations and trends are not official statistics.
const demoAreas = [
  11800, 11300, 5000, 15400, 20800, 14900, 18200, 9500, 12100, 19300, 22400, 27600, 8100, 15500,
]
const rows = [
  ['430100', '长沙市', '长沙', 2850, 21600, 71.2, 28.4, '长株潭', [112.9388, 28.2282]],
  ['430200', '株洲市', '株洲', 980, 6800, 64.5, 25.6, '长株潭', [113.1517, 27.8358]],
  ['430300', '湘潭市', '湘潭', 720, 5100, 62.8, 24.1, '长株潭', [112.9441, 27.8298]],
  ['430400', '衡阳市', '衡阳', 1120, 7900, 60.3, 22.8, '湘南', [112.6077, 26.9004]],
  ['430500', '邵阳市', '邵阳', 680, 4200, 49.6, 19.2, '湘中', [111.4679, 27.2389]],
  ['430600', '岳阳市', '岳阳', 1060, 7300, 61.4, 23.5, '洞庭湖', [113.1329, 29.3703]],
  ['430700', '常德市', '常德', 950, 6200, 58.7, 21.8, '洞庭湖', [111.6985, 29.0317]],
  ['430800', '张家界市', '张家界', 310, 1800, 43.2, 18.6, '湘西', [110.4792, 29.1171]],
  ['430900', '益阳市', '益阳', 540, 3500, 52.1, 20.4, '洞庭湖', [112.355, 28.5701]],
  ['431000', '郴州市', '郴州', 830, 5600, 56.9, 26.3, '湘南', [113.0147, 25.7705]],
  ['431100', '永州市', '永州', 610, 3900, 48.5, 21.7, '湘南', [111.6134, 26.4204]],
  ['431200', '怀化市', '怀化', 580, 3600, 45.8, 20.2, '湘西', [109.9782, 27.5501]],
  ['431300', '娄底市', '娄底', 490, 3200, 51.3, 19.8, '湘中', [112.0085, 27.7281]],
  ['433100', '湘西土家族苗族自治州', '湘西州', 280, 1600, 39.6, 17.5, '湘西', [109.7389, 28.3117]],
]
export const cities = rows.map(
  ([code, name, shortName, stations, piles, fastRate, growth, region, center], i) => ({
    code,
    name,
    shortName,
    stations,
    piles,
    fastRate,
    growth,
    region,
    center,
    areaKm2: demoAreas[i],
    density: Number(((stations / demoAreas[i]) * 100).toFixed(2)),
  }),
)
export const sourceInfo = {
  simulated: true,
  updatedAt: '2026-09-30',
  period: '2026年第三季度',
  label: '本地演示数据',
  boundary: '阿里云 DataV.GeoAtlas（展示边界）',
  note: '设施数量、统计面积、密度、趋势及站点位置均为模拟数据，不代表实际建设情况。',
}
export const trend = [
  { period: '2024 Q1', stations: 5820, piles: 32800 },
  { period: '2024 Q2', stations: 6270, piles: 36200 },
  { period: '2024 Q3', stations: 6880, piles: 41500 },
  { period: '2024 Q4', stations: 7620, piles: 47900 },
  { period: '2025 Q1', stations: 8250, piles: 53800 },
  { period: '2025 Q2', stations: 8960, piles: 60400 },
  { period: '2025 Q3', stations: 9730, piles: 66400 },
  { period: '2025 Q4', stations: 10360, piles: 71300 },
  { period: '2026 Q1', stations: 11080, piles: 76200 },
  { period: '2026 Q2', stations: 11720, piles: 81500 },
  {
    period: '2026 Q3',
    stations: cities.reduce((n, c) => n + c.stations, 0),
    piles: cities.reduce((n, c) => n + c.piles, 0),
  },
]
// A few illustrative markers per city, never fetched from POI services.
export const stations = cities.flatMap((city, i) =>
  [0, 1, 2].map((j) => ({
    id: `${city.code}-${j}`,
    cityCode: city.code,
    name: `${city.shortName}示例充电站 ${j + 1}`,
    type: j === 1 ? '交流慢充' : '直流快充',
    position: [city.center[0] + (j - 1) * 0.085, city.center[1] + (j - 1) * 0.06],
    piles: 8 + ((i + j) % 6) * 4,
  })),
)
export const provinceMetrics = [
  {
    key: 'stations',
    label: '充电站总量',
    value: cities.reduce((n, c) => n + c.stations, 0),
    unit: '座',
    change: '较上季度 +2.4%',
    icon: 'station',
  },
  {
    key: 'piles',
    label: '公共充电桩',
    value: cities.reduce((n, c) => n + c.piles, 0),
    unit: '个',
    change: '较上季度 +1.0%',
    icon: 'bolt',
  },
  {
    key: 'cities',
    label: '统计市州',
    value: 14,
    unit: '个',
    change: '全省14市州',
    icon: 'city',
  },
  {
    key: 'fast',
    label: '直流快充占比',
    value: Number(
      (
        cities.reduce((n, c) => n + c.piles * c.fastRate, 0) /
        cities.reduce((n, c) => n + c.piles, 0)
      ).toFixed(1),
    ),
    unit: '%',
    change: '直流桩数量 / 公共充电桩总量',
    icon: 'speed',
  },
]
export const regionalGroups = ['长株潭', '洞庭湖', '湘南', '湘中', '湘西'].map((name) => ({
  name,
  stations: cities.filter((c) => c.region === name).reduce((n, c) => n + c.stations, 0),
}))

// All synthetic series are generated in fixtures, never in view components.
export const cityTrends = Object.fromEntries(
  cities.map((city) => [
    city.code,
    trend.map((row) => ({
      period: row.period,
      stations: Math.round((row.stations * city.stations) / trend.at(-1).stations),
      piles: Math.round((row.piles * city.piles) / trend.at(-1).piles),
    })),
  ]),
)
export const analysisGroups = {
  region: regionalGroups.map((group) => ({
    key: group.name,
    label: group.name,
    cityCodes: cities.filter((c) => c.region === group.name).map((c) => c.code),
  })),
  scale: [
    {
      key: 'high',
      label: '1,000座及以上',
      cityCodes: cities.filter((c) => c.stations >= 1000).map((c) => c.code),
    },
    {
      key: 'middle',
      label: '500–999座',
      cityCodes: cities.filter((c) => c.stations >= 500 && c.stations < 1000).map((c) => c.code),
    },
    {
      key: 'low',
      label: '不足500座',
      cityCodes: cities.filter((c) => c.stations < 500).map((c) => c.code),
    },
  ],
}
for (const groups of Object.values(analysisGroups))
  for (const group of groups) {
    const members = cities.filter((c) => group.cityCodes.includes(c.code))
    group.stations = members.reduce((sum, c) => sum + c.stations, 0)
    group.piles = members.reduce((sum, c) => sum + c.piles, 0)
    group.trend = trend.map((row, i) => ({
      period: row.period,
      stations: members.reduce((sum, c) => sum + cityTrends[c.code][i].stations, 0),
      piles: members.reduce((sum, c) => sum + cityTrends[c.code][i].piles, 0),
    }))
  }
for (const metric of provinceMetrics) {
  if (['stations', 'piles'].includes(metric.key)) {
    const values = trend.map((row) => row[metric.key])
    metric.sparkline = values.slice(-8)
    metric.yoy = Number(((values.at(-1) / values.at(-5) - 1) * 100).toFixed(1))
    metric.qoq = Number(((values.at(-1) / values.at(-2) - 1) * 100).toFixed(1))
    metric.change = '期末存量 · 最近8个季度'
  }
}
provinceMetrics.find((m) => m.key === 'cities').change = '14市州 · 统一统计口径'
provinceMetrics.find((m) => m.key === 'fast').change = '按公共充电桩数量加权汇总'
