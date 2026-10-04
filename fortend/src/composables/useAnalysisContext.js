import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { cityMapConfig } from '@/config/maps'
import { parseAnalysisFilters, analysisFilterQuery } from '@/utils/analysis-filters'
export function useAnalysisContext() {
  const route = useRoute(),
    router = useRouter(),
    analysis = useAnalysisStore(),
    dashboard = useDashboardStore()
  let applying = false
  watch(
    () => route.fullPath,
    () => {
      applying = true
      try {
        const state = parseAnalysisFilters(
          route.query,
          route.name === 'city' ? String(route.params.cityCode) : '',
          Object.keys(cityMapConfig),
        )
        analysis.$patch({ ...state, filterError: '' })
        dashboard.selectCity(state.cityCode)
        analysis.load()
      } catch (error) {
        analysis.filterError = error.message
      } finally {
        applying = false
      }
    },
    { immediate: true },
  )
  watch(
    () => [
      analysis.cityCode,
      analysis.districtCode,
      analysis.classification,
      analysis.reviewStatus,
      analysis.needsReview,
      analysis.batch,
      analysis.activeMetric,
      analysis.filterError,
    ],
    () => {
      if (applying || analysis.filterError) return
      const query = { ...route.query }
      for (const key of [
        'city',
        'district',
        'classification',
        'review_status',
        'needs_review',
        'batch',
        'metric',
      ])
        delete query[key]
      Object.assign(
        query,
        analysisFilterQuery(analysis, route.name === 'city' ? String(route.params.cityCode) : ''),
      )
      if (
        ['city', 'district', 'classification', 'review_status', 'needs_review', 'batch'].some(
          (key) => query[key] !== route.query[key],
        )
      )
        delete query.station
      if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ query })
      dashboard.selectCity(analysis.cityCode)
      analysis.load()
    },
  )
}
