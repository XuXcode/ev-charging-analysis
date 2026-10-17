import { ref } from 'vue'

/**
 * Offline demo fallback.
 *
 * When the FastAPI backend is unreachable the UI would only be able to show its error states,
 * which makes the layout impossible to review. The builders in `demo/offline-snapshot.js`
 * replay values that were recorded offline and ship with this repository; they are never
 * presented as live statistics and the top bar labels them.
 *
 * Explicit opt-in: VITE_DEMO_FALLBACK=auto; disabled by default.
 */
export const demoMode = ref(false)

const fallbackSources = new Set()

const enabled = import.meta.env.VITE_DEMO_FALLBACK === 'auto'

// Only transport-level failures fall back. Cancelled requests are normal (the analysis store
// aborts superseded loads) and a 404 is a real answer from a working backend, so both rethrow.
function isTransportFailure(error) {
  if (!error) return false
  if (error.code === 'ERR_CANCELED' || error.name === 'CanceledError') return false
  if (typeof error.status === 'number') return error.status >= 500
  return true
}

export function withDemoFallback(request, build, label) {
  return request()
    .then((payload) => {
      fallbackSources.delete(label)
      demoMode.value = fallbackSources.size > 0
      return payload
    })
    .catch((error) => {
      if (!enabled || !isTransportFailure(error)) throw error
      let payload
      try {
        payload = build()
      } catch {
        throw error
      }
      if (payload === null || payload === undefined) throw error
      const wasOffline = demoMode.value
      fallbackSources.add(label)
      demoMode.value = true
      if (!wasOffline) {
        console.warn(
          `[演示数据] 后端接口不可用，${label}改用仓库内离线快照。该快照用于界面演示，不是实时统计，接口恢复后自动失效。`,
        )
      }
      return payload
    })
}
