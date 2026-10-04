import test from 'node:test'
import assert from 'node:assert/strict'
import { coreFindings } from '../../src/utils/findings.js'
test('missing inputs do not manufacture conclusions', () => {
  assert.deepEqual(coreFindings(null), [])
  assert.deepEqual(coreFindings({ province: { count: 0 }, cities: [] }), [])
})
test('findings change with real input and preserve the straight sample coverage caveat', () => {
  const data = {
    province: { count: 10, coveragePercent: 2 },
    cities: [
      { name: '甲', code: '1', count: 4, coveragePercent: 1 },
      { name: '乙', code: '2', count: 6, coveragePercent: 3 },
    ],
  }
  assert.match(coreFindings(data)[0].text, /乙.*6条.*60%/)
  assert.match(coreFindings(data)[1].text, /1%—3%/)
  assert.match(coreFindings(data)[2].text, /不代表道路出行或人口覆盖/)
  data.cities[0].count = 8
  data.cities[1].count = 2
  assert.match(coreFindings(data)[0].text, /甲.*8条.*80%/)
})
