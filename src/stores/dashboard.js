import { defineStore } from 'pinia'
import { getDashboard, getStoredStations, getCollectionSummary } from '@/api/dashboard'
let collectionRequest
export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    cities: [],
    stations: [],
    metrics: [],
    trend: [],
    regions: [],
    sourceInfo: null,
    loading: false,
    error: '',
    loaded: false,
    rankingMetric: 'stations',
    selectedCityCode: '',
    hoveredCityCode: '',
    selectedGroup: null,
    hoveredGroupCodes: [],
    cityTrends: {},
    analysisGroups: {},
    indicatorDefinitions: [],
    groupDefinitions: [],
    reservedCharts: [],
    stationQuery: null,
    stationQueryLoading: false,
    stationQueryError: '',
    stationQueryVersion: 0,
    collectionInfo: null,
    collectionError: '',
  }),
  getters: {
    ranking: (state) =>
      [...state.cities].sort(
        (a, b) =>
          Number.isFinite(b[state.rankingMetric]) - Number.isFinite(a[state.rankingMetric]) ||
          (b[state.rankingMetric] || 0) - (a[state.rankingMetric] || 0),
      ),
    totalStations: (state) =>
      state.cities.length && state.cities.every((c) => Number.isFinite(c.stations))
        ? state.cities.reduce((n, c) => n + c.stations, 0)
        : null,
    selectedCity: (state) => state.cities.find((c) => c.code === state.selectedCityCode),
    selectedCodes: (state) =>
      state.selectedCityCode ? [state.selectedCityCode] : state.selectedGroup?.cityCodes || [],
    highlightedCodes: (state) =>
      state.hoveredCityCode ? [state.hoveredCityCode] : state.hoveredGroupCodes,
    activeIndicator: (state) =>
      state.indicatorDefinitions.find((item) => item.key === state.rankingMetric),
    analysisLabel: (state) =>
      state.cities.find((c) => c.code === state.selectedCityCode)?.shortName ||
      state.selectedGroup?.label ||
      '全省',
    analysisTrend: (state) =>
      state.cityTrends[state.selectedCityCode] || state.selectedGroup?.trend || state.trend,
  },
  actions: {
    async queryCityStations(code, page = 1) {
      const version = ++this.stationQueryVersion
      this.stationQueryLoading = true
      this.stationQueryError = ''
      this.stations = []
      this.stationQuery = null
      try {
        const result = await getStoredStations(code, page)
        if (version !== this.stationQueryVersion) return
        this.stations = result.items
        this.stationQuery = {
          ...result,
          returnedCount: result.items.length,
          mayHaveMore: result.page * result.pageSize < result.total,
        }
        await this.loadCollectionInfo()
      } catch (error) {
        if (version === this.stationQueryVersion) this.stationQueryError = error.message
      } finally {
        if (version === this.stationQueryVersion) this.stationQueryLoading = false
      }
    },
    clearStationQuery() {
      ++this.stationQueryVersion
      this.stations = []
      this.stationQuery = null
      this.stationQueryError = ''
      this.stationQueryLoading = false
    },
    async loadCollectionInfo() {
      if (collectionRequest) return collectionRequest
      this.collectionError = ''
      collectionRequest = getCollectionSummary()
        .then((data) => {
          this.collectionInfo = data
        })
        .catch((error) => {
          this.collectionError = error.message
        })
        .finally(() => {
          collectionRequest = null
        })
      return collectionRequest
    },
    selectCity(code) {
      this.selectedCityCode = code
      this.selectedGroup = null
    },
    selectGroup(group) {
      this.selectedGroup = group
      this.selectedCityCode = ''
    },
    clearSelection() {
      this.selectedCityCode = ''
      this.selectedGroup = null
      this.hoveredCityCode = ''
      this.hoveredGroupCodes = []
    },
    hoverCity(code = '') {
      this.hoveredCityCode = code
      this.hoveredGroupCodes = []
    },
    async load() {
      if (this.loading) return
      this.loading = true
      this.error = ''
      try {
        const data = await getDashboard()
        if (
          !Array.isArray(data.cities) ||
          !Array.isArray(data.stations) ||
          !Array.isArray(data.metrics) ||
          !Array.isArray(data.trend) ||
          !Array.isArray(data.regions) ||
          !Array.isArray(data.indicatorDefinitions) ||
          !Array.isArray(data.groupDefinitions) ||
          !Array.isArray(data.reservedCharts) ||
          !data.analysisGroups ||
          !data.cityTrends ||
          !data.sourceInfo
        )
          throw new Error('接口数据结构不符合约定')
        if (
          !data.cities.every(
            (city) =>
              ['stations', 'piles', 'density', 'areaKm2'].every(
                (key) => city[key] === null || Number.isFinite(city[key]),
              ) &&
              (city.areaKm2 === null || city.areaKm2 > 0),
          ) ||
          !['stations', 'piles', 'density'].every((key) =>
            data.indicatorDefinitions.some((d) => d.key === key),
          )
        )
          throw new Error('接口缺少有效的市州指标或指标口径')
        // Station data has its own paginated lifecycle; avoid overwriting a city query.
        const { stations: _stations, ...dashboard } = data
        this.$patch(dashboard)
        this.loaded = true
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },
  },
})
