import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { http } from '../../src/api/http.js'

test('API unwraps envelopes and preserves cancellation, timeout and trace metadata', async () => {
  const original = http.defaults.adapter
  try {
    http.defaults.adapter = (config) =>
      Promise.resolve({ data: { code: 200, data: { count: 0 } }, status: 200, config })
    assert.deepEqual(await http.get('/test'), { count: 0 })
    const cancel = new axios.CanceledError('cancelled')
    http.defaults.adapter = () => Promise.reject(cancel)
    await assert.rejects(http.get('/test'), (error) => error === cancel)
    http.defaults.adapter = () => Promise.reject({ code: 'ECONNABORTED' })
    await assert.rejects(http.get('/test'), /请求超时/)
    http.defaults.adapter = () =>
      Promise.reject({
        response: {
          status: 422,
          data: { message: '参数无效' },
          headers: { 'x-request-id': 'trace-test' },
        },
      })
    await assert.rejects(
      http.get('/test'),
      (error) =>
        error.status === 422 && error.requestId === 'trace-test' && error.message === '参数无效',
    )
  } finally {
    http.defaults.adapter = original
  }
})
