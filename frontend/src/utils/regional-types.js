export function regionalTypes(rows) {
  const valid = rows.filter((r) =>
    [r.density, r.coveragePercent].every(
      (v) => typeof v === 'number' && Number.isFinite(v) && v >= 0,
    ),
  )
  if (valid.length < 2) return { items: [], thresholds: null }
  const median = (values) => {
    const sorted = [...values].sort((a, b) => a - b)
    const i = Math.floor(sorted.length / 2)
    return sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2
  }
  const density = median(valid.map((r) => r.density)),
    coveragePercent = median(valid.map((r) => r.coveragePercent))
  const differentiated = new Set(valid.map((r) => `${r.density}:${r.coveragePercent}`)).size > 1
  const items = rows.map((r) => ({
    ...r,
    type: !valid.includes(r)
      ? '数据不足'
      : !differentiated
        ? '差异不足'
        : r.density >= density
          ? r.coveragePercent >= coveragePercent
            ? '高密高覆盖'
            : '高密低覆盖'
          : r.coveragePercent >= coveragePercent
            ? '低密高覆盖'
            : '低密低覆盖',
  }))
  return { items, thresholds: { density, coveragePercent } }
}
