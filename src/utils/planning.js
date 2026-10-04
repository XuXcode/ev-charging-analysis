// Missing observations remain distinct from measured low accessibility.
export function lowAccessibility(regions, { cityCode = '', districtCode = '', minutes = 15 } = {}) {
  const scoped = regions.filter(
    (row) =>
      (!cityCode || row.cityCode === cityCode) && (!districtCode || row.adcode === districtCode),
  )
  return {
    low: scoped
      .filter(
        (row) =>
          row.complete &&
          Number.isFinite(row.durationSeconds) &&
          row.durationSeconds > minutes * 60,
      )
      .sort((a, b) => b.durationSeconds - a.durationSeconds || a.adcode.localeCompare(b.adcode)),
    unknown: scoped.filter((row) => !row.complete || !Number.isFinite(row.durationSeconds)),
    notice: '区县代表点候选道路观测，不代表人口、面积覆盖或高需求低供给。',
  }
}
