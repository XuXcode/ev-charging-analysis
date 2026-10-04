import { ref, shallowRef, onScopeDispose } from 'vue'
import { getStoredStations } from '../api/dashboard.js'

export function useStationSearch() {
  const items = shallowRef([]),
    total = ref(0),
    loading = ref(false),
    error = ref(''),
    page = ref(1)
  const pageSize = 8
  let controller,
    timer,
    generation = 0
  function cancel() {
    generation++
    clearTimeout(timer)
    controller?.abort()
    controller = null
    loading.value = false
  }
  function search(text, filters, nextPage = 1, immediate = false) {
    cancel()
    items.value = []
    total.value = 0
    error.value = ''
    page.value = nextPage
    if (!text.trim()) return
    const version = generation
    loading.value = true
    const run = async () => {
      const current = new AbortController()
      controller = current
      try {
        const data = await getStoredStations(filters.city, nextPage, {
          ...filters,
          keyword: text.trim(),
          pageSize,
          signal: current.signal,
        })
        if (version !== generation) return
        if (
          !Array.isArray(data.items) ||
          !Number.isInteger(data.total) ||
          data.total < 0 ||
          data.page !== nextPage
        )
          throw new Error('站点检索返回结构不符合约定')
        items.value = data.items
        total.value = data.total
      } catch (failure) {
        if (version === generation && !current.signal.aborted) error.value = failure.message
      } finally {
        if (version === generation) {
          controller = null
          loading.value = false
        }
      }
    }
    if (immediate) return run()
    timer = setTimeout(run, 350)
  }
  onScopeDispose(cancel)
  return { items, total, loading, error, page, pageSize, search, cancel }
}
