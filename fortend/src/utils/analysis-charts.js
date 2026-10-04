import { escapeHtml, formatNumber } from './format'
import { token } from './chart-theme'

// Render existing snapshot values only. No analysis or estimated business values here.
export const comparisonMetrics = [
  { key: 'count', label: 'POI样本数量', unit: '条', precision: 0 },
  { key: 'density', label: 'POI样本密度', unit: '条/km²', precision: 3 },
  { key: 'coveragePercent', label: '1km样本覆盖率', unit: '%', precision: 2 },
]
const grid = { left: 20, right: 36, top: 38, bottom: 30, containLabel: true }
const splitLine = { lineStyle: { color: token('chart-grid'), type: 'dashed' } }
export function comparisonOption(rows, metric, selected) {
  const ordered = [...rows].sort((a, b) => b[metric.key] - a[metric.key])
  return {
    grid,
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params) => {
        const row = ordered[params[0].dataIndex]
        return `${escapeHtml(row.name)}<br/>${escapeHtml(metric.label)}：${formatNumber(row[metric.key], metric.precision)} ${escapeHtml(metric.unit)}<br/>POI样本口径${row.completenessWarning ? '<br/><b>检索触及上限：样本可能不完整</b>' : ''}`
      },
    },
    xAxis: { type: 'value', name: metric.unit, splitLine },
    yAxis: { type: 'category', inverse: true, data: ordered.map((r) => r.name) },
    series: [
      {
        type: 'bar',
        barMaxWidth: 22,
        data: ordered.map((r) => ({
          value: r[metric.key],
          cityCode: r.level === 'district' ? r.cityCode : r.code,
          regionCode: r.code,
          regionName: r.name,
          warning: r.completenessWarning,
          itemStyle: {
            color: !selected || selected === r.code ? token('primary') : token('chart-muted'),
            borderRadius: [0, 4, 4, 0],
          },
        })),
      },
    ],
  }
}
export function coverageDistribution(rows) {
  const ordered = [...rows].sort((a, b) => a.coveragePercent - b.coveragePercent)
  return {
    grid,
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p) =>
        `${escapeHtml(p.data.regionName)}<br/>1km直线样本覆盖率：${formatNumber(p.value[0], 2)}%<br/>累计区县比例：${formatNumber(p.value[1], 2)}%<br/>区县等权，不是面积加权覆盖率${p.data.warning ? '<br/><b>检索触及上限：样本可能不完整</b>' : ''}`,
    },
    xAxis: { type: 'value', min: 0, max: 100, name: '覆盖率 %', splitLine },
    yAxis: { type: 'value', min: 0, max: 100, name: '累计区县 %', splitLine },
    series: [
      {
        type: 'line',
        step: 'end',
        symbolSize: 5,
        lineStyle: { color: '#217765', width: 2 },
        itemStyle: { color: '#217765' },
        data: ordered.map((r, i) => ({
          value: [r.coveragePercent, ((i + 1) / ordered.length) * 100],
          cityCode: r.cityCode,
          regionName: r.name,
          regionCode: r.code,
          warning: r.completenessWarning,
        })),
      },
    ],
  }
}
export function densityCoverageOption(rows) {
  return {
    grid,
    tooltip: {
      confine: true,
      formatter: (p) =>
        `${escapeHtml(p.data.regionName)}<br/>POI样本密度：${formatNumber(p.value[0], 3)} 条/km²<br/>1km直线样本覆盖率：${formatNumber(p.value[1], 2)}%<br/>POI样本数量：${formatNumber(p.data.count)} 条${p.data.warning ? '<br/>检索触及上限，样本可能不完整' : ''}`,
    },
    xAxis: { type: 'value', name: '条/km²', splitLine },
    yAxis: { type: 'value', name: '覆盖率 %', splitLine },
    series: [
      {
        type: 'scatter',
        symbolSize: 15,
        itemStyle: { color: '#217765', opacity: 0.8 },
        emphasis: {
          itemStyle: { color: '#c49943' },
          label: { show: true, formatter: (p) => p.data.regionName },
        },
        data: rows.map((r) => ({
          value: [r.density, r.coveragePercent],
          cityCode: r.code,
          regionName: r.name,
          count: r.count,
          warning: r.completenessWarning,
        })),
      },
    ],
  }
}
