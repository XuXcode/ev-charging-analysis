import { test } from 'node:test'
import assert from 'node:assert/strict'
import { lowAccessibility } from '../../src/utils/planning.js'
test('measured road time identifies low accessibility while unknown stays separate', () => {
  const rows = [
    { adcode: '430102', cityCode: '430100', complete: true, durationSeconds: 0 },
    { adcode: '430103', cityCode: '430100', complete: true, durationSeconds: 900 },
    { adcode: '430104', cityCode: '430100', complete: true, durationSeconds: 901 },
    { adcode: '430105', cityCode: '430100', complete: false, durationSeconds: 1200 },
    { adcode: '430106', cityCode: '430100', complete: true, durationSeconds: null },
  ]
  const result = lowAccessibility(rows, { minutes: 15 })
  assert.deepEqual(
    result.low.map((r) => r.adcode),
    ['430104'],
  )
  assert.deepEqual(
    result.unknown.map((r) => r.adcode),
    ['430105', '430106'],
  )
  assert.match(result.notice, /代表点/)
})
test('city and county selection exclude unrelated accessibility findings', () => {
  const rows = [
    { adcode: '430102', cityCode: '430100', complete: true, durationSeconds: 600 },
    { adcode: '430202', cityCode: '430200', complete: true, durationSeconds: 1200 },
  ]
  assert.equal(lowAccessibility(rows, { cityCode: '430100', minutes: 5 }).low.length, 1)
  assert.equal(
    lowAccessibility(rows, { cityCode: '430100', districtCode: '430202', minutes: 5 }).low.length,
    0,
  )
  assert.equal(lowAccessibility([], {}).low.length, 0)
})
