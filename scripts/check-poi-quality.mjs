import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { auditMatchesSummary, getPoiNameHints } from '../src/utils/poiQuality.js'

const audit = JSON.parse(
  readFileSync(new URL('../public/data-quality/poi-audit.json', import.meta.url)),
)
const summary = {
  storedCount: audit.stationCount,
  updatedAt: audit.sourceUpdatedAt,
  latestRun: { id: audit.runId },
}
assert.equal(auditMatchesSummary(audit, summary), true)
assert.equal(auditMatchesSummary(audit, { ...summary, storedCount: audit.stationCount + 1 }), false)
assert.equal(auditMatchesSummary(audit, { ...summary, updatedAt: '2026-01-01T00:00:00Z' }), false)
assert.equal(auditMatchesSummary(audit, { ...summary, latestRun: { id: 'different-run' } }), false)
assert.equal(auditMatchesSummary({ ...audit, readOnly: false }, summary), false)
assert.equal(auditMatchesSummary(null, summary), false)
assert.equal(auditMatchesSummary(audit, { ...summary, updatedAt: 'invalid-date' }), false)
assert.deepEqual(getPoiNameHints('普通充电站'), []) // Absence of hints is not a positive operating verdict.
assert.deepEqual(
  getPoiNameHints('充电站(已拆除)(暂停营业)').map((h) => h.label),
  ['暂停营业', '已拆除'],
)
assert.equal(
  getPoiNameHints('充电站(内部专用)').some((h) => h.group === 'access'),
  true,
)
assert.equal(
  getPoiNameHints('锂萌换电').some((h) => h.group === 'category'),
  true,
)
assert.equal(
  Object.values(audit.cities).reduce((sum, value) => sum + value, 0),
  audit.stationCount,
)
assert.equal(
  audit.rawTypes.reduce((sum, row) => sum + row.count, 0),
  audit.stationCount,
)
assert.ok(audit.reviewUniqueCount <= audit.stationCount)
assert.ok(
  audit.pausedOrRemovedUniqueCount <=
    (audit.statusHints['暂停营业'] || 0) + (audit.statusHints['已拆除'] || 0),
)
assert.equal(audit.boundary.featureCount, 14)
assert.equal(audit.boundary.uniqueCityCodeCount, 14)
assert.equal(audit.boundary.invalidCoordinates, 0)
assert.equal(audit.boundary.unclosedRings, 0)
console.log(
  'POI quality checks passed: snapshot freshness, name hints, real audit totals and 14-city geometry.',
)
