import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import {
  cities,
  stations,
  provinceMetrics,
  trend,
  regionalGroups,
  sourceInfo,
  cityTrends,
  analysisGroups,
} from '../src/mock/data.js'
import { indicatorDefinitions, groupDefinitions, reservedCharts } from '../src/mock/analysis.js'
import { topics, cityModules } from '../src/mock/topics.js'
const geometry = JSON.parse(
  await readFile(new URL('../src/assets/hunan.geojson.json', import.meta.url)),
)
assert.equal(cities.length, 14)
assert.equal(new Set(cities.map((c) => c.code)).size, 14)
assert.equal(geometry.features.length, 14)
for (const city of cities) {
  assert(
    geometry.features.some((f) => String(f.properties.adcode) === city.code),
    `${city.name}: missing boundary`,
  )
  assert(city.piles > city.stations && city.fastRate >= 0 && city.fastRate <= 100)
  assert(stations.filter((s) => s.cityCode === city.code).length > 0)
  assert(Number.isFinite(city.areaKm2) && city.areaKm2 > 0)
  assert.equal(city.density, Number(((city.stations / city.areaKm2) * 100).toFixed(2)))
  assert.deepEqual(
    cityTrends[city.code].map((row) => row.period),
    trend.map((row) => row.period),
  )
  assert.equal(cityTrends[city.code].at(-1).stations, city.stations)
  assert.equal(cityTrends[city.code].at(-1).piles, city.piles)
}
for (const station of stations) {
  assert(cities.some((c) => c.code === station.cityCode))
  assert.equal(station.position.length, 2)
  assert(station.position.every(Number.isFinite))
}
const totalStations = cities.reduce((n, c) => n + c.stations, 0)
const totalPiles = cities.reduce((n, c) => n + c.piles, 0)
assert.equal(provinceMetrics.find((m) => m.key === 'stations').value, totalStations)
assert.equal(provinceMetrics.find((m) => m.key === 'piles').value, totalPiles)
assert.equal(trend.at(-1).stations, totalStations)
assert.equal(trend.at(-1).piles, totalPiles)
assert.equal(
  regionalGroups.reduce((n, r) => n + r.stations, 0),
  totalStations,
)
assert.equal(topics.length, 6)
assert.equal(cityModules.length, 7)
assert(sourceInfo.simulated)
for (const definition of groupDefinitions) {
  const groups = analysisGroups[definition.key]
  const codes = groups.flatMap((group) => group.cityCodes)
  assert.equal(codes.length, 14)
  assert.equal(new Set(codes).size, 14)
  assert.deepEqual([...codes].sort(), cities.map((city) => city.code).sort())
  for (const group of groups) {
    const members = cities.filter((city) => group.cityCodes.includes(city.code))
    for (const metric of ['stations', 'piles']) {
      assert.equal(
        group[metric],
        members.reduce((sum, city) => sum + city[metric], 0),
      )
      assert.equal(group.trend.at(-1)[metric], group[metric])
    }
  }
}
assert.deepEqual(
  indicatorDefinitions.map((d) => d.key),
  ['stations', 'piles', 'density'],
)
assert.equal(reservedCharts.length, 4)
for (const metric of provinceMetrics.filter((m) => m.sparkline)) {
  assert.equal(metric.sparkline.length, 8)
  assert.equal(metric.sparkline.at(-1), metric.value)
  assert.equal(metric.yoy, Number(((metric.value / trend.at(-5)[metric.key] - 1) * 100).toFixed(1)))
  assert.equal(metric.qoq, Number(((metric.value / trend.at(-2)[metric.key] - 1) * 100).toFixed(1)))
}
console.log(
  `Fixture checks passed: 14 boundaries, ${stations.length} markers, ${totalStations} stations, ${totalPiles} piles, 6 topics, 7 city modules.`,
)
