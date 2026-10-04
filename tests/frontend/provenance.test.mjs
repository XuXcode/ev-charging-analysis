import test from 'node:test'
import assert from 'node:assert/strict'
import { snapshotProvenance } from '../../src/utils/analysis-provenance.js'

test('portable evidence retains multiple batches and frozen snapshot filters including false', () => {
  const snapshot = {
    snapshotId: 'snapshot',
    computedAt: '2026-10-04T00:00:00Z',
    metadata: {
      runId: 'foundation',
      qualityRunIds: ['foundation', 'supplement'],
      datasetQualityRunIds: ['foundation', 'supplement'],
      filters: { classification: 'public_candidate', needsReview: false },
      parameters: { radiusM: 1000, bufferSegments: 256 },
      frozenInputHash: 'hash',
      algorithmVersion: 'v1.2',
      sourceUpdatedAt: '2026-10-03T00:00:00Z',
      notice: '直线覆盖，不证明道路可达',
    },
  }
  const evidence = snapshotProvenance(snapshot)
  assert.equal(evidence.qualityBatches, 'foundation / supplement')
  assert.equal(evidence.frozenInputHash, 'hash')
  assert.equal(evidence.computedAt, snapshot.computedAt)
  assert.deepEqual(JSON.parse(evidence.filters), snapshot.metadata.filters)
  assert.deepEqual(JSON.parse(evidence.parameters), snapshot.metadata.parameters)
  assert.equal(evidence.limitations, snapshot.metadata.notice)
  assert.deepEqual(snapshotProvenance(null), {})
})
