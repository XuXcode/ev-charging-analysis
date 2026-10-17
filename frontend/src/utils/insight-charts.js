import { classificationLabels, reviewStatusLabels } from '@/config/analysis'
import { escapeHtml, formatNumber } from '@/utils/format'
import { roadMetrics } from '@/utils/road-accessibility'

const colors = ['#23775b', '#66a58b', '#94b9a3', '#c39858', '#879c94']
const base = () => ({
  color: colors,
  grid: { left: 56, right: 26, top: 28, bottom: 36 },
  tooltip: { trigger: 'axis', confine: true },
  xAxis: { type: 'category', axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', name: '个', minInterval: 1, nameTextStyle: { fontSize: 11 } },
})
const axisTips = (unit, note = '') => ({
  trigger: 'axis',
  formatter: (rows) =>
    `${escapeHtml(rows[0]?.name || '')}<br/>${rows.map((p) => `${escapeHtml(p.seriesName)}：${formatNumber(p.value, 0)} ${escapeHtml(unit)}`).join('<br/>')}${note ? `<br/>${escapeHtml(note)}` : ''}`,
})
function histogram(values, bounds) {
  return bounds.map((b, index) => ({
    name: b.name,
    value: values.filter((v) => (index === 0 ? v >= b.min : v > b.min) && v <= b.max).length,
  }))
}
export function qualityCharts(data) {
  const rows = data?.rows || [],
    total = rows.reduce((s, r) => s + r.count, 0)
  const categories = [...new Set(rows.map((r) => r.classification))]
  const pieRows = categories.map((c) => ({
    name: classificationLabels[c],
    value: rows.filter((r) => r.classification === c).reduce((s, r) => s + r.count, 0),
    insightClassification: c,
    unit: '条',
  }))
  const pie = {
    color: colors,
    tooltip: {
      trigger: 'item',
      formatter: (p) =>
        `${escapeHtml(p.name)}<br/>POI样本：${formatNumber(p.value)} 条<br/>占当前口径：${p.percent}%`,
    },
    legend: { orient: 'vertical', right: 8, top: 'middle', textStyle: { fontSize: 11 } },
    series: [
      {
        name: 'POI分类',
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['35%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        emphasis: { label: { show: true, formatter: '{b}\n{d}%', fontSize: 12 } },
        unit: '条',
        data: pieRows,
      },
    ],
  }
  const stacked = {
    ...base(),
    tooltip: axisTips('条', '人工复核状态不等于实际营业状态'),
    legend: { bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 48, right: 18, top: 28, bottom: 55 },
    xAxis: {
      type: 'category',
      data: categories.map((c) => classificationLabels[c]),
      axisLabel: { fontSize: 11, interval: 0 },
    },
    yAxis: { type: 'value', name: '条', minInterval: 1 },
    series: Object.entries(reviewStatusLabels).map(([status, label], i) => ({
      type: 'bar',
      name: label,
      unit: '条',
      stack: 'reviews',
      barMaxWidth: 42,
      itemStyle: { color: colors[i] },
      data: categories.map((c) => ({
        value: rows.find((r) => r.classification === c && r.review_status === status)?.count || 0,
        insightClassification: c,
      })),
    })),
  }
  const pending = rows
    .filter((r) => r.review_status === 'unreviewed')
    .reduce((s, r) => s + r.count, 0)
  return {
    total,
    pie,
    stacked,
    pieNote: `${categories.length}类、${formatNumber(total)}条当前治理记录。点击类别可联动筛选；选择“全部类别”可比较构成。`,
    qualityNote: total
      ? `未复核记录占${formatNumber((pending / total) * 100, 1)}%；核验状态反映治理进度，不证明设施营业。`
      : '当前治理口径没有记录。',
  }
}
export function gridCharts(rows) {
  const total = rows.reduce((s, r) => s + r.count, 0),
    n = rows.length
  const bins = histogram(
    rows.map((r) => r.density),
    [
      { name: '0', min: 0, max: 0 },
      { name: '(0,.04]', min: 0, max: 0.04 },
      { name: '(.04,.1]', min: 0.04, max: 0.1 },
      { name: '(.1,.25]', min: 0.1, max: 0.25 },
      { name: '(.25,.5]', min: 0.25, max: 0.5 },
      { name: '(.5,1]', min: 0.5, max: 1 },
      { name: '>1', min: 1, max: Infinity },
    ],
  )
  const density = {
    ...base(),
    tooltip: axisTips('个网格', '横轴单位：条/km²；包含零样本网格'),
    xAxis: {
      type: 'category',
      data: bins.map((b) => b.name),
      axisLabel: { fontSize: 10, interval: 0 },
    },
    yAxis: { type: 'value', name: '网格数', minInterval: 1 },
    series: [
      {
        name: '5km网格',
        type: 'bar',
        unit: '个网格',
        data: bins.map((b) => b.value),
        barMaxWidth: 38,
        itemStyle: { color: '#478f70', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
  const ranked = [...rows].sort((a, b) => b.count - a.count),
    groups = Math.min(20, n),
    sums = [],
    cumulative = []
  let previous = 0,
    acc = 0
  for (let i = 1; i <= groups; i++) {
    const end = Math.ceil((n * i) / groups),
      subtotal = ranked.slice(previous, end).reduce((s, r) => s + r.count, 0)
    sums.push({
      name: `${formatNumber((previous / n) * 100, 0)}–${formatNumber((end / n) * 100, 0)}%`,
      value: subtotal,
    })
    acc += subtotal
    cumulative.push(total ? (acc / total) * 100 : 0)
    previous = end
  }
  const pareto = {
    ...base(),
    grid: { left: 52, right: 48, top: 28, bottom: 42 },
    tooltip: {
      trigger: 'axis',
      formatter: (items) =>
        `${escapeHtml(items[0]?.name || '')} 网格分组<br/>${items.map((p) => `${escapeHtml(p.seriesName)}：${formatNumber(p.value, p.seriesIndex === 1 ? 1 : 0)} ${p.seriesIndex === 1 ? '%' : '条'}`).join('<br/>')}<br/>按样本数降序，网格不作行政区内再裁切`,
    },
    xAxis: {
      type: 'category',
      data: sums.map((s) => s.name),
      axisLabel: { fontSize: 10, interval: 3 },
    },
    yAxis: [
      { type: 'value', name: '样本条数', minInterval: 1 },
      { type: 'value', name: '累计 %', min: 0, max: 100, splitLine: { show: false } },
    ],
    series: [
      {
        name: '组内样本',
        type: 'bar',
        unit: '条',
        data: sums.map((s) => s.value),
        itemStyle: { color: '#86b69c' },
        barMaxWidth: 28,
      },
      {
        name: '累计样本占比',
        type: 'line',
        unit: '%',
        yAxisIndex: 1,
        data: cumulative,
        showSymbol: false,
        lineStyle: { width: 2.5, color: '#176d50' },
      },
    ],
  }
  const top = ranked.slice(0, Math.ceil(n * 0.2)).reduce((s, r) => s + r.count, 0),
    zeros = rows.filter((r) => r.count === 0).length
  return {
    density,
    pareto,
    total,
    positive: n - zeros,
    densityNote: n
      ? `零样本网格${formatNumber(zeros)}个（${formatNumber((zeros / n) * 100, 1)}%）。密度按实际裁切面积计算，边缘小网格可能偏高。`
      : '尚无当前口径网格。',
    paretoNote: total
      ? `样本最多的前20%网格包含${formatNumber((top / total) * 100, 1)}%网格归属样本；分母${formatNumber(total)}条，与行政编码归属计数可能不同。`
      : '网格内没有样本，不计算累计样本占比。',
  }
}
export function lisaChart(data) {
  const names = { HH: '高—高', LL: '低—低', HL: '高—低', LH: '低—高', NS: '不显著' },
    keys = Object.keys(names)
  return {
    ...base(),
    tooltip: axisTips('个网格', '全省固定网格的既有FDR分类，不重新计算局部显著性'),
    xAxis: {
      type: 'category',
      data: keys.map((k) => names[k]),
      axisLabel: { fontSize: 11, interval: 0 },
    },
    yAxis: { type: 'value', name: '网格数', minInterval: 1 },
    series: [
      {
        name: 'LISA分类',
        type: 'bar',
        unit: '个网格',
        data: keys.map((k, i) => ({
          value: data?.counts[k] || 0,
          itemStyle: { color: colors[i] },
        })),
        barMaxWidth: 40,
      },
    ],
  }
}
export function roadCharts(data) {
  const rows = data?.regions || [],
    observed = rows.filter((r) => r.complete && Number.isFinite(r.durationSeconds))
  const bins = histogram(
    observed.map((r) => r.durationSeconds / 60),
    [
      { name: '≤5', min: 0, max: 5 },
      { name: '(5,10]', min: 5, max: 10 },
      { name: '(10,15]', min: 10, max: 15 },
      { name: '(15,30]', min: 15, max: 30 },
      { name: '(30,60]', min: 30, max: 60 },
      { name: '>60', min: 60, max: Infinity },
    ],
  )
  const distribution = {
    ...base(),
    tooltip: axisTips('个代表点', '区县几何代表点；不是人口或面积覆盖率'),
    xAxis: {
      type: 'category',
      name: '分钟',
      data: bins.map((b) => b.name),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', name: '代表点数', minInterval: 1 },
    series: [
      {
        name: '驾车观测',
        type: 'bar',
        unit: '个代表点',
        data: bins.map((b) => b.value),
        barMaxWidth: 40,
        itemStyle: { color: '#589a7b', borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
  const values = [5, 10, 15].map((m) => roadMetrics(rows, m)),
    denominator = values[0]?.resolved || 0
  const curve = {
    ...base(),
    tooltip: {
      trigger: 'axis',
      formatter: (items) =>
        `${items[0]?.name} 分钟<br/>代表点可达比例：${formatNumber(items[0]?.value, 1)}%<br/>分母：${denominator}个完整起点；未完成起点单列`,
    },
    xAxis: { type: 'category', name: '分钟', data: ['5', '10', '15'] },
    yAxis: { type: 'value', name: '代表点比例 %', min: 0, max: 100 },
    series: [
      {
        name: '代表点可达比例',
        type: 'line',
        unit: '%',
        data: values.map((v) => v.percent),
        symbolSize: 8,
        lineStyle: { width: 3, color: '#23775b' },
        itemStyle: { color: '#23775b' },
        areaStyle: { color: 'rgba(57,133,92,.10)' },
      },
    ],
  }
  return {
    distribution,
    curve,
    denominator,
    observed: observed.length,
    distributionNote: `${observed.length}个代表点有完整道路时间；${rows.length - observed.length}个未完成或无有效路线的代表点未进入直方图。`,
    curveNote: denominator
      ? `分母为${denominator}个完整起点，10分钟内${values[1].reached}个（${formatNumber(values[1].percent, 1)}%）。三点连线仅连接阈值观测，非人口或面积覆盖。`
      : '没有完整起点，不计算可达比例。',
  }
}
export function relationChart(rows) {
  return {
    ...base(),
    tooltip: {
      trigger: 'item',
      formatter: (p) =>
        `${escapeHtml(p.data.regionName)}<br/>POI样本密度：${formatNumber(p.value[0], 3)} 条/km²<br/>1km直线样本覆盖率：${formatNumber(p.value[1], 2)}%<br/>样本：${formatNumber(p.data.count)}条${p.data.warning ? '<br/>样本可能不完整' : ''}`,
    },
    grid: { left: 58, right: 32, top: 30, bottom: 50 },
    xAxis: { type: 'value', name: '条/km²', min: 0, nameLocation: 'middle', nameGap: 26 },
    yAxis: { type: 'value', name: '直线覆盖 %', min: 0 },
    series: [
      {
        name: '区域',
        type: 'scatter',
        unit: '%',
        data: rows.map((r) => ({
          name: r.name,
          regionName: r.name,
          cityCode: r.cityCode || r.code,
          regionCode: r.code,
          count: r.count,
          warning: r.completenessWarning,
          value: [r.density, r.coveragePercent],
        })),
        symbolSize: 14,
        itemStyle: { color: '#308868', opacity: 0.8 },
        emphasis: { itemStyle: { color: '#195c44', borderColor: '#fff', borderWidth: 2 } },
      },
    ],
  }
}
