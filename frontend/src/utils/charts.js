import { escapeHtml, formatNumber } from './format'
import { chartTheme, token } from './chart-theme'
const colors = chartTheme.color
export const chartBase = {
  color: colors,
  textStyle: chartTheme.textStyle,
  animationDuration: 240,
  tooltip: {
    ...chartTheme.tooltip,
    trigger: 'axis',
    confine: true,
    backgroundColor: '#fff',
    borderColor: '#dbe5df',
    textStyle: { color: '#243b35', fontSize: 13 },
    padding: [12, 14],
  },
  grid: { left: 14, right: 20, bottom: 8, top: 30, containLabel: true },
}
export function comparisonOption(
  cities,
  metric = 'samples',
  definition,
  selectedCodes = [],
  simulated = false,
) {
  const ordered = [...cities].sort((a, b) => b[metric] - a[metric])
  const unit = definition?.unit || '条'
  const label = definition?.label || 'POI样本数量'
  const available = cities.filter((c) => Number.isFinite(c[metric]))
  const average = available.length
    ? available.reduce((sum, c) => sum + c[metric], 0) / available.length
    : null
  return {
    ...chartBase,
    tooltip: {
      ...chartBase.tooltip,
      formatter: (params) => {
        const c = ordered[params[0].dataIndex]
        return `${escapeHtml(c.name)}<br/>${escapeHtml(label)} <b>${formatNumber(c[metric], definition?.precision)} ${escapeHtml(unit)}</b><br/><small style="display:block;max-width:320px;white-space:normal;line-height:1.7">${escapeHtml(definition?.description || '高德可检索POI样本，不代表官方设施总量')}<br/>${simulated ? '模拟数据 · ' : ''}${metric === 'samples' ? '点击进入市州详情' : '点击联动市州'}</small>`
      },
    },
    xAxis: {
      type: 'category',
      data: ordered.map((c) => c.shortName),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#dce5e1' } },
      axisLabel: { interval: 0, fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      name: unit,
      splitNumber: metric === 'samples' ? 3 : 5,
      splitLine: { lineStyle: { color: '#e5ece6', type: 'dashed' } },
    },
    series: [
      {
        name: label,
        type: 'bar',
        barMaxWidth: 24,
        data: ordered.map((c, i) => ({
          value: c[metric],
          cityCode: c.code,
          regionName: c.name,
          warning: c.completenessWarning,
          itemStyle: {
            color: selectedCodes.length
              ? selectedCodes.includes(c.code)
                ? '#217765'
                : '#d0dfd6'
              : i === 0
                ? '#217765'
                : '#91bdaf',
            borderRadius: [3, 3, 0, 0],
          },
        })),
        emphasis: { itemStyle: { color: '#337b5e' } },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#a17d46', width: 1, type: 'dashed' },
          label: {
            position: 'insideEndTop',
            color: '#856739',
            fontSize: 11,
            formatter: `市州均值 ${formatNumber(average, 1)}`,
          },
          data: available.length === cities.length ? [{ yAxis: average }] : [],
        },
      },
    ],
  }
}
