import test from 'node:test'
import assert from 'node:assert/strict'
import { districtMapScope, searchLoadedStations } from '../../src/utils/map-scope.js'

test('county drilldown accepts catalog membership without using an unrelated city', () => {
  const catalog = [{ code: '430102', cityCode: '430100', name: '芙蓉区' }]
  assert.deepEqual(districtMapScope('430102', '430100', catalog), {
    cityCode: '430100',
    districtCode: '430102',
    name: '芙蓉区',
  })
  for (const [district, city] of [
    ['', '430100'],
    ['430199', '430100'],
    ['430102', '430200'],
    ['430102', ''],
  ])
    assert.equal(districtMapScope(district, city, catalog), null)
})

test('loaded station search preserves scope, handles missing address and caps visible results', () => {
  const stations = Array.from({ length: 12 }, (_, index) => ({
    id: index,
    name: `站点${index}`,
    address: index === 0 ? '人民路' : null,
    poiId: `B${index}`,
  }))
  assert.equal(searchLoadedStations(stations, ' 人民路 ').items[0].id, 0)
  assert.equal(searchLoadedStations(stations, 'b11').items[0].id, 11)
  assert.equal(searchLoadedStations(stations, '站点').total, 12)
  assert.equal(searchLoadedStations(stations, '站点').items.length, 8)
  assert.deepEqual(searchLoadedStations(stations, '不存在'), { total: 0, items: [] })
  assert.deepEqual(searchLoadedStations(stations, ' '), { total: 0, items: [] })
})
