import tokens from '../config/design-tokens.json'
const flat = Object.assign({}, ...Object.values(tokens))
export function token(name) {
  const value = flat[name]
  return value?.startsWith('var(') ? token(value.slice(6, -1)) : value
}
export const mapPalette = [0, 1, 2, 3].map((i) => token(`map-scale-${i}`))
export const themeName = 'hunan-light'
export const chartTheme = {
  color: ['green-600', 'blue-600', 'amber-700', 'green-400'].map(token),
  backgroundColor: 'transparent',
  textStyle: { fontFamily: token('font-family'), fontSize: 13, color: token('text-secondary') },
  categoryAxis: axis(),
  valueAxis: axis(),
  legend: { textStyle: { color: token('text-secondary'), fontSize: 13 }, icon: 'roundRect' },
  tooltip: {
    confine: true,
    backgroundColor: token('surface'),
    borderColor: token('border'),
    textStyle: { color: token('text'), fontSize: 14 },
    padding: [12, 16],
    extraCssText: 'max-width:360px;white-space:normal;line-height:1.7;',
  },
  line: { symbolSize: 6, lineStyle: { width: 2.5 } },
  bar: { barMaxWidth: 24 },
}
function axis() {
  return {
    axisLine: { lineStyle: { color: token('border') } },
    axisTick: { show: false },
    axisLabel: { color: token('muted'), fontSize: 13, hideOverlap: true },
    nameTextStyle: { color: token('text-secondary'), fontSize: 13 },
    splitLine: { lineStyle: { color: token('chart-grid'), type: 'dashed' } },
  }
}
export function themedOption(option, reducedMotion = false) {
  return {
    animationDuration: 240,
    animationDurationUpdate: 200,
    ...option,
    animation: reducedMotion ? false : (option.animation ?? true),
    tooltip: { ...chartTheme.tooltip, ...option.tooltip },
  }
}
