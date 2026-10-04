import test from 'node:test'
import assert from 'node:assert/strict'
import { regionalDistribution, sortRegions } from '../../src/utils/regional-statistics.js'
test('county quartiles exclude missing values, preserve real zero and flag only distribution extremes', () => {
  const rows = [0, 1, 2, 3, 4, 5, 100, null, NaN].map((value, index) => ({
    code: String(index),
    density: value,
  }))
  const result = regionalDistribution(rows, 'density')
  assert.equal(result.count, 7)
  assert.equal(result.missingCount, 2)
  assert.equal(result.q1, 1.5)
  assert.equal(result.median, 3)
  assert.equal(result.q3, 4.5)
  assert.deepEqual(result.outliers, [{ code: '6', direction: '高端' }])
  assert.equal(sortRegions(rows, 'density', true)[0].density, 0)
  assert.equal(sortRegions(rows, 'density')[0].density, 100)
  assert.equal(rows[0].density, 0)
})
test('small or degenerate distributions do not invent outliers or replace empty input with zero', () => {
  assert.equal(regionalDistribution([], 'count').median, null)
  assert.deepEqual(
    regionalDistribution(
      [1, 2, 100].map((count, index) => ({ code: String(index), count })),
      'count',
    ).outliers,
    [],
  )
  assert.deepEqual(
    regionalDistribution(
      [1, 1, 1, 1, 100].map((count, index) => ({ code: String(index), count })),
      'count',
    ).outliers,
    [],
  )
})
