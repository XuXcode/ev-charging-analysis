import test from 'node:test'
import assert from 'node:assert/strict'
import { roadMetrics, roadCurve } from '../../src/utils/road-accessibility.js'

test('road ratios exclude incomplete origins, retain zero and use distinct mean denominator', () => {
  const rows = [
    { complete: true, durationSeconds: 0, distanceM: 0, thresholdReached: { 5: true } },
    { complete: true, durationSeconds: 600, distanceM: 3000, thresholdReached: { 5: false } },
    { complete: true, durationSeconds: null, distanceM: null, thresholdReached: { 5: false } },
    { complete: false, durationSeconds: 100, distanceM: 1000, thresholdReached: { 5: null } },
  ]
  assert.deepEqual(roadMetrics(rows, 5), {
    total: 4,
    resolved: 3,
    measured: 2,
    reached: 1,
    percent: 100 / 3,
    meanMinutes: 5,
    meanDistanceKm: 1.5,
  })
  assert.deepEqual(roadCurve(rows), [
    [0, 100 / 3],
    [10, 200 / 3],
  ])
  assert.equal(roadMetrics([], 15).percent, null)
  assert.equal(roadMetrics([{ complete: false }], 10).meanMinutes, null)
})
