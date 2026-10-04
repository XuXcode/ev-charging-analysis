import test from 'node:test'
import assert from 'node:assert/strict'
import { analysisSummary } from '../../src/utils/analysis-summary.js'
test('copied summary uses selected county and truthful filters rather than province totals', () => {
  const snapshot = {
    metadata: { runId: 'batch', algorithmVersion: 'v1', sourceUpdatedAt: '2026-10-03T00:00:00Z' },
    snapshotId: 'snapshot',
    province: { count: 10745, coveragePercent: 6 },
    cities: [{ code: '430100', name: '长沙市', count: 1700, coveragePercent: 13 }],
    districts: [
      { code: '430102', name: '芙蓉区', count: 0, coveragePercent: 0, completenessWarning: true },
    ],
  }
  const summary = analysisSummary(snapshot, {
    cityCode: '430100',
    districtCode: '430102',
    classification: 'personal',
    reviewStatus: 'confirmed',
  })
  assert.match(summary, /芙蓉区/)
  assert.match(summary, /样本数量：0条/)
  assert.match(summary, /分类：个人/)
  assert.match(summary, /复核状态：已确认/)
  assert.match(summary, /样本可能不完整/)
  assert.doesNotMatch(summary, /10745条|1700条/)
  assert.throws(() => analysisSummary(snapshot, { districtCode: 'wrong' }))
})
