import test from 'node:test'
import assert from 'node:assert/strict'
import {
  parseAnalysisFilters,
  analysisFilterQuery,
  cityAnalysisRoute,
} from '../../src/utils/analysis-filters.js'
const cities = ['430100', '430200']
test('analysis context survives URL round-trip without duplicate city params', () => {
  const state = parseAnalysisFilters(
    {
      city: '430100',
      district: '430102',
      classification: 'personal',
      review_status: 'unreviewed',
      metric: 'density',
      batch: 'a'.repeat(32),
    },
    '',
    cities,
  )
  assert.deepEqual(parseAnalysisFilters(analysisFilterQuery(state), '', cities), state)
  assert.equal(analysisFilterQuery(state, '430100').city, undefined)
  const cityRoute = cityAnalysisRoute(state, '430200')
  assert.equal(cityRoute.path, '/city/430200')
  assert.equal(cityRoute.query.classification, 'personal')
  assert.equal(cityRoute.query.district, undefined)
  assert.deepEqual(parseAnalysisFilters({}, '', cities), {
    cityCode: '',
    districtCode: '',
    classification: 'public_candidate',
    reviewStatus: '',
    needsReview: false,
    batch: '',
    activeMetric: 'count',
  })
})
test('public candidate is default and all samples remains an explicit reproducible URL scope', () => {
  const all = parseAnalysisFilters({ classification: 'all' }, '', cities)
  assert.equal(all.classification, '')
  assert.equal(analysisFilterQuery(all).classification, 'all')
  const publicScope = parseAnalysisFilters({}, '', cities)
  assert.equal(publicScope.classification, 'public_candidate')
  assert.deepEqual(parseAnalysisFilters(analysisFilterQuery(publicScope), '', cities), publicScope)
})
test('reject mismatched counties, unknown city, duplicate and invalid filter values', () => {
  for (const query of [
    { city: '430100', district: '430202' },
    { city: '439900' },
    { city: ['430100'] },
    { classification: 'fabricated' },
    { review_status: 'done' },
    { batch: 'x' },
    { metric: 'demand' },
    { needs_review: 'false' },
    { needs_review: ['true'] },
  ])
    assert.throws(() => parseAnalysisFilters(query, '', cities))
})

test('review clue scope is distinct from manual review status and survives routes', () => {
  const state = parseAnalysisFilters(
    { classification: 'all', needs_review: 'true', review_status: 'unreviewed' },
    '',
    cities,
  )
  assert.equal(state.needsReview, true)
  assert.equal(state.reviewStatus, 'unreviewed')
  assert.deepEqual(parseAnalysisFilters(analysisFilterQuery(state), '', cities), state)
  assert.equal(cityAnalysisRoute(state, '430100').query.needs_review, 'true')
})
