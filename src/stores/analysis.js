import { defineStore } from 'pinia'
import { getAnalysisSnapshot, getAnalysisBoundaries } from '../api/analysis.js'
import { defaultClassification } from '../utils/analysis-filters.js'
const requests = new WeakMap()
const boundaries = new Map()
export const useAnalysisStore = defineStore('analysis', {
  state: () => ({
    snapshot: null,
    activeMetric: 'count',
    loading: false,
    error: '',
    pending: false,
    cityCode: '',
    districtCode: '',
    classification: defaultClassification,
    reviewStatus: '',
    needsReview: false,
    batch: '',
    filterError: '',
    loadedKey: '',
    districtCatalog: [],
    selectedStation: null,
  }),
  getters: {
    definition: (state) =>
      state.snapshot?.indicatorDefinitions.find((item) => item.key === state.activeMetric),
    cities: (state) => state.snapshot?.cities || [],
    districts: (state) => state.snapshot?.districts || [],
  },
  actions: {
    async load(force = false) {
      if (this.filterError) return
      const params = {
        classification: this.classification || undefined,
        review_status: this.reviewStatus || undefined,
        needs_review: this.needsReview || undefined,
        batch: this.batch || undefined,
      }
      const key = JSON.stringify(params)
      const existing = requests.get(this)
      if (existing?.key === key) return existing.promise
      if (this.snapshot && this.loadedKey === key && !force) return
      existing?.controller.abort()
      const controller = new AbortController()
      const current = { key, controller }
      requests.set(this, current)
      this.snapshot = null
      this.loading = true
      this.error = ''
      this.pending = false
      current.promise = getAnalysisSnapshot(params, controller.signal)
        .then((data) => {
          if (requests.get(this) !== current) return
          this.snapshot = data
          this.loadedKey = key
          this.districtCatalog = data.districts
        })
        .catch((error) => {
          if (requests.get(this) !== current || controller.signal.aborted) return
          this.error = error.message
          this.pending = error.status === 404
        })
        .finally(() => {
          if (requests.get(this) !== current) return
          this.loading = false
          requests.delete(this)
        })
      return current.promise
    },
    resetFilters(cityCode = '') {
      this.$patch({
        cityCode,
        districtCode: '',
        classification: defaultClassification,
        reviewStatus: '',
        needsReview: false,
        batch: '',
        activeMetric: 'count',
        filterError: '',
      })
    },
    async boundaries(parent, signal) {
      const key = `${this.snapshot?.metadata.boundaryHash}:${parent}`
      if (!boundaries.has(key)) boundaries.set(key, await getAnalysisBoundaries(parent, signal))
      return boundaries.get(key)
    },
  },
})
