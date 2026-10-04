// Descriptive comparisons of a single real snapshot; no service-risk classification.
export function quantile(sorted, probability) {
  if (!sorted.length) return null
  const position = (sorted.length - 1) * probability
  const lower = Math.floor(position)
  return sorted[lower] + (sorted[Math.ceil(position)] - sorted[lower]) * (position - lower)
}
export function regionalDistribution(rows, metric) {
  const valid = rows.filter((row) => Number.isFinite(row[metric]))
  const values = valid.map((row) => row[metric]).sort((a, b) => a - b)
  const q1 = quantile(values, 0.25),
    median = quantile(values, 0.5),
    q3 = quantile(values, 0.75)
  const iqr = values.length ? q3 - q1 : null
  const eligible = values.length >= 4 && iqr > 0
  const lower = eligible ? q1 - 1.5 * iqr : null
  const upper = eligible ? q3 + 1.5 * iqr : null
  return {
    count: valid.length,
    missingCount: rows.length - valid.length,
    q1,
    median,
    q3,
    iqr,
    lower,
    upper,
    outliers: eligible
      ? valid
          .filter((row) => row[metric] < lower || row[metric] > upper)
          .map((row) => ({ code: row.code, direction: row[metric] < lower ? '低端' : '高端' }))
      : [],
    status:
      values.length < 4
        ? '少于4个有效区县，不标注异常值'
        : iqr === 0
          ? '四分位距为0，不标注异常值'
          : 'Q1−1.5×IQR与Q3+1.5×IQR之外的分布异常值',
  }
}
export function sortRegions(rows, metric, ascending = false) {
  return [...rows].sort((a, b) => {
    if (!Number.isFinite(a[metric]))
      return Number.isFinite(b[metric]) ? 1 : a.code.localeCompare(b.code)
    if (!Number.isFinite(b[metric])) return -1
    return (
      (ascending ? a[metric] - b[metric] : b[metric] - a[metric]) || a.code.localeCompare(b.code)
    )
  })
}
