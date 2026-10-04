/** Ratios describe equally weighted representative origins, never area/population coverage. */
export function roadMetrics(rows, minutes) {
  const resolved = rows.filter((row) => row.complete === true)
  const measured = resolved.filter((row) => Number.isFinite(row.durationSeconds))
  const reached = resolved.filter((row) => row.thresholdReached?.[String(minutes)] === true)
  return {
    total: rows.length,
    resolved: resolved.length,
    measured: measured.length,
    reached: reached.length,
    percent: resolved.length ? (100 * reached.length) / resolved.length : null,
    meanMinutes: measured.length
      ? measured.reduce((sum, row) => sum + row.durationSeconds, 0) / measured.length / 60
      : null,
    meanDistanceKm: measured.length
      ? measured.reduce((sum, row) => sum + row.distanceM, 0) / measured.length / 1000
      : null,
  }
}

export function roadCurve(rows) {
  const resolved = rows.filter((row) => row.complete === true)
  return resolved
    .filter((row) => Number.isFinite(row.durationSeconds))
    .sort((a, b) => a.durationSeconds - b.durationSeconds)
    .map((row, index) => [row.durationSeconds / 60, (100 * (index + 1)) / resolved.length])
}
