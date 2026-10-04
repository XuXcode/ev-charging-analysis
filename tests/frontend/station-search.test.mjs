import test from 'node:test'
import assert from 'node:assert/strict'
import { effectScope } from 'vue'
import { http } from '../../src/api/http.js'
import { useStationSearch } from '../../src/composables/useStationSearch.js'

test('database search cancels stale responses, preserves compound filters and paginates', async () => {
  const original = http.defaults.adapter
  const requests = []
  http.defaults.adapter = (config) => new Promise((resolve) => requests.push({ config, resolve }))
  const scope = effectScope()
  const search = scope.run(() => useStationSearch())
  try {
    const first = search.search('旧结果', { city: '430100' }, 1, true)
    await Promise.resolve()
    const second = search.search(
      '新结果',
      { city: '430200', adcode: '430202', classification: 'public_candidate' },
      2,
      true,
    )
    await Promise.resolve()
    assert.equal(requests[0].config.signal.aborted, true)
    assert.deepEqual(requests[1].config.params, {
      city: '430200',
      bbox: undefined,
      adcode: '430202',
      classification: 'public_candidate',
      review_status: undefined,
      needs_review: undefined,
      batch: undefined,
      keyword: '新结果',
      page: 2,
      page_size: 8,
      real_only: true,
    })
    requests[1].resolve({
      data: { items: [{ id: 'new' }], total: 12, page: 2 },
      status: 200,
      headers: {},
      config: requests[1].config,
    })
    await second
    requests[0].resolve({
      data: { items: [{ id: 'old' }], total: 1, page: 1 },
      status: 200,
      headers: {},
      config: requests[0].config,
    })
    await first
    assert.equal(search.items.value[0].id, 'new')
    assert.equal(search.page.value, 2)
    search.search(' ', {})
    assert.equal(search.items.value.length, 0)
    assert.equal(search.loading.value, false)
  } finally {
    scope.stop()
    http.defaults.adapter = original
  }
})
