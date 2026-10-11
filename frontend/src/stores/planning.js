import { defineStore } from 'pinia'
import { getPlanningSnapshot, getPlanningLayer } from '../api/planning.js'
let request
export const usePlanningStore = defineStore('planning', {
  state: () => ({
    snapshot: null,
    loading: false,
    error: '',
    pending: false,
    cityCode: '',
    districtCode: '',
    layer: 'planning',
    loaded: false,
  }),
  getters: {
    definition: (state) =>
      state.snapshot?.indicatorDefinitions.find((item) => item.key === 'planningScore'),
    topDistricts: (state) => state.snapshot?.summary?.topDistricts || [],
  },
  actions: {
    async load(force = false) {
      if (this.loading && !force) return
      this.loading = true
      this.error = ''
      this.pending = false
      try {
        const data = await getPlanningSnapshot({})
        this.snapshot = data
        this.loaded = true
      } catch (error) {
        this.error = error.message
        this.pending = error.status === 404
      } finally {
        this.loading = false
      }
    },
    async layer(params, signal) {
      return getPlanningLayer(params, signal)
    },
    resetFilters() {
      this.$patch({ cityCode: '', districtCode: '', error: '' })
    },
  },
})