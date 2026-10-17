import { shallowRef, ref, watch, onBeforeUnmount } from 'vue'
import { useAnalysisStore } from '@/stores/analysis'
import { insightSnapshot, insightLayer, insightRoad, insightQuality } from '@/api/insights'

const emptyErrors = () => ({ quality: '', spatial: '', grid: '', lisa: '', road: '' })
export function useInsights() {
  const analysis = useAnalysisStore()
  const snapshot = shallowRef(null),
    quality = shallowRef(null),
    grid = shallowRef([]),
    lisa = shallowRef(null),
    road = shallowRef(null)
  const errors = ref(emptyErrors()),
    loading = ref({ quality: false, spatial: false, grid: false, lisa: false, road: false })
  const unavailable = ref({})
  let controller
  async function load() {
    controller?.abort()
    const current = new AbortController(),
      signal = current.signal
    controller = current
    snapshot.value = quality.value = lisa.value = road.value = null
    grid.value = []
    errors.value = emptyErrors()
    unavailable.value = {}
    loading.value = { quality: true, spatial: true, grid: true, lisa: true, road: true }
    const selection = {
      city: analysis.cityCode,
      adcode: analysis.districtCode,
      classification: analysis.classification,
      batch: analysis.batch,
      reviewStatus: analysis.reviewStatus,
      needsReview: analysis.needsReview,
    }
    if (analysis.filterError) {
      errors.value = Object.fromEntries(
        Object.keys(emptyErrors()).map((k) => [k, analysis.filterError]),
      )
      Object.keys(loading.value).forEach((k) => (loading.value[k] = false))
      return
    }
    const filters = {
      classification: selection.classification || undefined,
      batch: selection.batch || undefined,
      review_status: selection.reviewStatus || undefined,
      needs_review: selection.needsReview || undefined,
    }
    const active = () => controller === current && !signal.aborted
    async function task(key, action) {
      try {
        await action()
      } catch (e) {
        if (active()) {
          errors.value[key] = e.message
          unavailable.value[key] = e.status === 404
        }
      } finally {
        if (active()) loading.value[key] = false
      }
    }
    await Promise.allSettled([
      task('quality', async () => {
        const data = await insightQuality(
          { ...filters, adcode: selection.adcode || selection.city || undefined },
          signal,
        )
        if (active()) quality.value = data
      }),
      task('road', async () => {
        const data = await insightRoad(
          {
            ...filters,
            classification: selection.classification || 'all',
            city_code: selection.city || undefined,
            adcode: selection.adcode || undefined,
          },
          signal,
        )
        if (active()) road.value = data
      }),
      task('spatial', async () => {
        let data
        try {
          data = await insightSnapshot(filters, signal)
          const actual = data.metadata?.filters || {}
          const batchMatches =
            (actual.batch || '') === selection.batch ||
            (!actual.batch &&
              data.metadata?.datasetQualityRunIds?.length === 1 &&
              data.metadata.datasetQualityRunIds[0] === selection.batch)
          if (
            (actual.classification || '') !== selection.classification ||
            (actual.reviewStatus || '') !== selection.reviewStatus ||
            (actual.needsReview == null ? '' : String(actual.needsReview)) !==
              (selection.needsReview ? 'true' : '') ||
            !batchMatches
          )
            throw new Error('快照筛选口径不一致，已停止展示')
          if (!active()) return
          snapshot.value = data
        } catch (e) {
          if (active()) {
            errors.value.grid = errors.value.lisa = e.message
            unavailable.value.grid = unavailable.value.lisa = e.status === 404
            loading.value.grid = loading.value.lisa = false
          }
          throw e
        }
        const params = {
          snapshot_id: data.snapshotId,
          city: selection.city || undefined,
          adcode: selection.adcode || undefined,
        }
        await task('grid', async () => {
          const layer = await insightLayer('grid', params, signal)
          if (layer.snapshotId !== data.snapshotId) throw new Error('网格版本与空间快照不匹配')
          const rows = layer.features.map((f) => f.properties)
          if (
            rows.some(
              (r) =>
                !Number.isFinite(r.count) ||
                r.count < 0 ||
                !Number.isFinite(r.density) ||
                r.density < 0,
            )
          )
            throw new Error('网格字段不完整，不展示推算值')
          if (active()) grid.value = rows
        })
        await task('lisa', async () => {
          if (errors.value.grid) throw new Error('网格版本尚未确认，LISA暂不展示')
          let counts
          if (!selection.city && !selection.adcode && data.metadata.lisa?.classCounts) {
            counts = data.metadata.lisa.classCounts
            if (Object.values(counts).reduce((a, b) => a + b, 0) !== grid.value.length)
              throw new Error('LISA与网格数量不匹配')
          } else {
            const layer = await insightLayer('lisa', params, signal)
            if (layer.snapshotId !== data.snapshotId || layer.features.length !== grid.value.length)
              throw new Error('LISA统计与网格范围不匹配')
            counts = {}
            for (const f of layer.features)
              counts[f.properties.lisaClass] = (counts[f.properties.lisaClass] || 0) + 1
          }
          if (active()) lisa.value = { counts, metadata: data.metadata.lisa }
        })
      }),
    ])
  }
  watch(
    () => [
      analysis.cityCode,
      analysis.districtCode,
      analysis.classification,
      analysis.batch,
      analysis.reviewStatus,
      analysis.needsReview,
      analysis.filterError,
    ],
    load,
    { immediate: true },
  )
  onBeforeUnmount(() => controller?.abort())
  return { snapshot, quality, grid, lisa, road, errors, unavailable, loading, load }
}
