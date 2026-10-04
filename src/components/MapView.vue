<script setup>
import { computed, defineAsyncComponent, ref, onMounted, watch } from 'vue'
import { useAnalysisStore } from '@/stores/analysis'
import { districtMapScope } from '@/utils/map-scope'
import ViewState from './ViewState.vue'
import { useRouter } from 'vue-router'
import { cityAnalysisRoute } from '@/utils/analysis-filters'
// A single entry point; each scale owns its renderer and request lifecycle.
// The overview stays thematic; a selected county switches to its scoped station map.
const CityMap = defineAsyncComponent(() => import('./maps/CityMap.vue'))
const SpatialMap = defineAsyncComponent(() => import('./maps/SpatialMap.vue'))
const ProvinceMap = defineAsyncComponent(() => import('./maps/ProvinceMap.vue'))
const ready = ref(false)
const analysis = useAnalysisStore()
const router = useRouter()
function selectStation(station) {
  analysis.selectedStation = station
  const target = cityAnalysisRoute(analysis, station.cityCode, station.adcode)
  target.query.station = station.poiId
  router.push(target)
}
onMounted(async () => {
  await analysis.load()
  ready.value = true
})
const props = defineProps({
  cityCode: { type: String, default: '' },
  districtCode: { type: String, default: '' },
  linked: Boolean,
  selectionOnly: Boolean,
  compact: Boolean,
  analysisLayers: Boolean,
  parentCode: { type: String, default: '430000' },
  initialLayer: { type: String, default: 'regions' },
  focusCode: { type: String, default: '' },
  scopeCode: { type: String, default: '' },
  stationDrilldown: { type: Boolean, default: true },
})
const districtScope = computed(() =>
  props.stationDrilldown && !props.cityCode
    ? districtMapScope(
        props.scopeCode || analysis.districtCode,
        analysis.cityCode,
        analysis.districtCatalog,
      )
    : null,
)
const thematicMode = ref(false)
const localLayer = ref('')
watch(
  () => districtScope.value?.districtCode,
  () => {
    thematicMode.value = false
    localLayer.value = ''
  },
)
const mapCityCode = computed(
  () => props.cityCode || (!thematicMode.value && districtScope.value?.cityCode) || '',
)
const mapDistrictCode = computed(() =>
  props.cityCode ? props.districtCode : districtScope.value?.districtCode || '',
)
const cityMap = ref(null)
const emit = defineEmits(['city-select', 'district-select', 'analysis-select'])
function selectDistrict(code) {
  if (!props.cityCode) analysis.districtCode = code
  emit('district-select', code)
}
function openAnalysis(key) {
  if (districtScope.value) {
    localLayer.value = key
    thematicMode.value = true
  }
  emit('analysis-select', key)
}
defineExpose({
  setHeatmapData: (data) => cityMap.value?.setHeatmapData(data),
  drillToDistrict: () => cityMap.value?.drillToDistrict(),
})
</script>
<template>
  <div class="map-view" :class="mapCityCode ? 'city-map-shell' : 'province-map-shell'">
    <div v-if="districtScope" class="map-drilldown-context">
      <span>{{ districtScope.name }} · {{ thematicMode ? '区县专题分析' : '区县真实站点' }}</span>
      <button v-if="thematicMode" type="button" @click="thematicMode = false">返回高德站点</button>
      <button type="button" @click="selectDistrict('')">返回专题地图</button>
    </div>
    <CityMap
      v-if="mapCityCode"
      ref="cityMap"
      :city-code="mapCityCode"
      :district-code="mapDistrictCode"
      @district-select="selectDistrict"
      @analysis-select="openAnalysis"
      @station-select="selectStation"
    />
    <SpatialMap
      v-else-if="analysis.snapshot && !analysis.loading"
      :selection-only="selectionOnly"
      :compact="compact"
      :layers="analysisLayers"
      :parent-code="districtScope?.cityCode || parentCode"
      :initial-layer="localLayer || initialLayer"
      :focus-code="districtScope?.districtCode || focusCode"
      :scope-code="districtScope?.districtCode || scopeCode"
      @city-select="emit('city-select', $event)"
      @district-select="selectDistrict"
    />
    <ProvinceMap
      v-else-if="
        ready &&
        !analysis.loading &&
        !analysis.classification &&
        !analysis.reviewStatus &&
        !analysis.needsReview &&
        !analysis.batch &&
        !analysis.pending
      "
      :linked="linked"
      :selection-only="selectionOnly"
      :compact="compact"
      @city-select="emit('city-select', $event)"
    />
    <ViewState
      v-else
      :kind="
        analysis.loading
          ? 'skeleton'
          : analysis.pending
            ? 'pending'
            : analysis.error
              ? 'error'
              : 'skeleton'
      "
      :title="
        analysis.loading
          ? '正在读取分析地图'
          : analysis.pending
            ? '当前筛选的分析快照待接入'
            : '分析地图暂不可用'
      "
      :description="analysis.error"
      @retry="analysis.load(true)"
    />
  </div>
</template>
<style scoped>
.city-map-shell {
  display: flex;
  flex-direction: column;
}
.city-map-shell > :deep(.city-map) {
  flex: 1;
  height: auto;
}
.map-drilldown-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  color: var(--primary-dark);
}
.map-drilldown-context button {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--primary-dark);
  padding: 6px 10px;
  min-height: 36px;
  cursor: pointer;
}
</style>
