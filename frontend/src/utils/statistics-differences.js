// A source discrepancy is a review clue, not proof of a comparable time series.
export function statisticDifferences(records = []) {
  const groups = new Map()
  for (const row of records) {
    if (
      !row.adcode ||
      !Number.isInteger(row.year) ||
      !row.metric ||
      !row.unit ||
      typeof row.value !== 'number' ||
      !Number.isFinite(row.value) ||
      row.value < 0
    )
      continue
    const key = JSON.stringify([row.adcode, row.year, row.metric, row.unit])
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(row)
  }
  return [...groups.values()]
    .filter((rows) => new Set(rows.map((row) => row.value)).size > 1)
    .map((rows) => ({
      adcode: rows[0].adcode,
      year: rows[0].year,
      metric: rows[0].metric,
      label: rows[0].label || rows[0].metric,
      unit: rows[0].unit,
      records: [...rows].sort(
        (a, b) => a.value - b.value || (a.sourceUrl || '').localeCompare(b.sourceUrl || ''),
      ),
      notice:
        '同年同指标的来源数值不同，统计时点和范围尚未确认可比；保留独立记录，不合并或计算增长率。',
    }))
    .sort(
      (a, b) =>
        b.year - a.year || a.adcode.localeCompare(b.adcode) || a.metric.localeCompare(b.metric),
    )
}
