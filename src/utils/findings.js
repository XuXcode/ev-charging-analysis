import { formatNumber } from './format.js'
/** Descriptive facts only; missing or inconsistent input yields no conclusion. */
export function coreFindings(snapshot) {
  const cities = snapshot?.cities || []
  const total = snapshot?.province?.count
  if (!cities.length || !Number.isFinite(total) || total <= 0) return []
  if (
    cities.some((row) => !Number.isFinite(row.count) || row.count < 0) ||
    cities.reduce((sum, row) => sum + row.count, 0) !== total
  )
    return []
  const byCount = [...cities]
    .filter((r) => Number.isFinite(r.count))
    .sort((a, b) => b.count - a.count)
  const byCoverage = [...cities]
    .filter((r) => Number.isFinite(r.coveragePercent))
    .sort((a, b) => b.coveragePercent - a.coveragePercent)
  const facts = []
  if (byCount.length && byCount[0].count <= total)
    facts.push({
      key: 'concentration',
      label: '样本集中',
      text: `${byCount[0].name}样本最多，${formatNumber(byCount[0].count)}条，占全省${formatNumber((byCount[0].count / total) * 100, 2)}%。`,
      code: byCount[0].code,
    })
  if (byCoverage.length > 1)
    facts.push({
      key: 'coverage-gap',
      label: '覆盖差异',
      text: `市州1km样本覆盖率为${formatNumber(byCoverage.at(-1).coveragePercent, 2)}%—${formatNumber(byCoverage[0].coveragePercent, 2)}%，最高为${byCoverage[0].name}。`,
      code: byCoverage[0].code,
    })
  if (Number.isFinite(snapshot.province.coveragePercent))
    facts.push({
      key: 'province-coverage',
      label: '全省覆盖',
      text: `1km直线样本覆盖率${formatNumber(snapshot.province.coveragePercent, 2)}%；反映几何范围，不代表道路出行或人口覆盖。`,
    })
  return facts
}
