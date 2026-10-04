import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { useAnalysisStore } from '../../src/stores/analysis.js'
import { http } from '../../src/api/http.js'

test('store deduplicates matching requests, cancels old filters and rejects stale results', async () => {
  setActivePinia(createPinia())
  const original = http.defaults.adapter
  const pending = []
  http.defaults.adapter = (config) => new Promise((resolve) => pending.push({ config, resolve }))
  try {
    const store = useAnalysisStore()
    const first = store.load()
    const duplicate = store.load()
    assert.equal(pending.length, 1)
    store.classification = 'personal'
    const next = store.load()
    assert.equal(pending.length, 2)
    assert.equal(pending[0].config.signal.aborted, true)
    const snapshot = { snapshotId: 'filtered', districts: [], cities: [], indicatorDefinitions: [] }
    pending[1].resolve({
      data: { code: 200, data: snapshot },
      status: 200,
      config: pending[1].config,
    })
    await next
    pending[0].resolve({
      data: { code: 200, data: { ...snapshot, snapshotId: 'old' } },
      status: 200,
      config: pending[0].config,
    })
    await Promise.all([first, duplicate])
    assert.equal(store.snapshot.snapshotId, 'filtered')
    assert.equal(store.loading, false)
    await store.load()
    assert.equal(pending.length, 2)
  } finally {
    http.defaults.adapter = original
  }
})

test('missing scoped snapshot stays pending and never shows the previous full dataset', async () => {
  setActivePinia(createPinia())
  const original = http.defaults.adapter
  http.defaults.adapter = (config) =>
    Promise.reject({ response: { status: 404, data: { message: '当前口径尚未计算' } }, config })
  try {
    const store = useAnalysisStore()
    store.snapshot = { province: { count: 10745 } }
    store.classification = 'personal'
    await store.load()
    assert.equal(store.snapshot, null)
    assert.equal(store.pending, true)
    assert.equal(store.error, '当前口径尚未计算')
    store.resetFilters()
    assert.equal(store.classification, 'public_candidate')
    assert.equal(store.activeMetric, 'count')
  } finally {
    http.defaults.adapter = original
  }
})
