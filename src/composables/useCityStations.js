import { onBeforeUnmount, ref, shallowRef } from 'vue'
import { getStoredStations } from '@/api/dashboard'

/** A map query consumes API pages internally and publishes one complete city/viewport result. */
export function useCityStations() {
  const stations = shallowRef([])
  const loading = ref(false)
  const error = ref('')
  const total = ref(null)
  const loadedCount = ref(0)
  let controller
  let version = 0
  let publishedScope = ''

  function cancel() {
    ++version
    controller?.abort()
    controller = null
    loading.value = false
  }

  async function load(cityCode, bbox, districtCode, filters = {}) {
    cancel()
    const currentVersion = version
    const requestController = new AbortController()
    controller = requestController
    const scopeKey = JSON.stringify([
      cityCode,
      districtCode || '',
      Object.entries(filters).sort(([a], [b]) => a.localeCompare(b)),
    ])
    // Keep overlays during viewport refresh; different administrative/filter scopes clear.
    if (scopeKey !== publishedScope) stations.value = []
    error.value = ''
    total.value = null
    loadedCount.value = 0
    if (!/^43\d{4}$/.test(cityCode || '') || !cityCode.endsWith('00')) {
      error.value = '请选择有效的湖南市州'
      return
    }
    loading.value = true
    try {
      if (
        districtCode &&
        (!/^43\d{4}$/.test(districtCode) ||
          districtCode.endsWith('00') ||
          !districtCode.startsWith(cityCode.slice(0, 4)))
      )
        throw new Error('区县不属于当前市州')
      const records = new Map()
      let page = 1
      let pageCount = 1
      while (page <= pageCount) {
        const result = await getStoredStations(cityCode, page, {
          ...filters,
          bbox,
          adcode: districtCode || undefined,
          signal: requestController.signal,
        })
        if (currentVersion !== version || requestController.signal.aborted) return
        if (
          !Array.isArray(result.items) ||
          !Number.isInteger(result.total) ||
          result.total < 0 ||
          !Number.isInteger(result.pageSize) ||
          result.pageSize < 1 ||
          result.page !== page
        )
          throw new Error('站点接口返回结构不符合约定')
        total.value = result.total
        pageCount = Math.max(1, Math.ceil(result.total / result.pageSize))
        if (pageCount > 1000) throw new Error('市州站点较多，请改用当前视野加载')
        for (const station of result.items) {
          if (
            station.cityCode !== cityCode ||
            (districtCode && station.adcode !== districtCode) ||
            station.simulated !== false ||
            !Array.isArray(station.position) ||
            station.position.length !== 2 ||
            !station.position.every(Number.isFinite)
          )
            throw new Error('站点接口返回了无效的市州或坐标记录')
          records.set(station.id, station)
        }
        loadedCount.value = records.size
        ++page
      }
      if (currentVersion === version) {
        publishedScope = scopeKey
        stations.value = [...records.values()]
      }
    } catch (cause) {
      if (currentVersion === version && !requestController.signal.aborted) {
        error.value = cause.message || '站点加载失败，请重试'
        stations.value = []
      }
    } finally {
      if (currentVersion === version) {
        loading.value = false
        controller = null
      }
    }
  }

  onBeforeUnmount(cancel)
  return { stations, loading, error, total, loadedCount, load, cancel }
}
