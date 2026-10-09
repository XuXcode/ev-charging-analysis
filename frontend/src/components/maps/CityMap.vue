<script>
// Cache successful provider boundaries across city routes, without changing stored POI data.
const districtBoundaryCache = new Map()
const cameraCache = new Map()
</script>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { cityMapConfig } from '@/config/maps'
import { useCityStations } from '@/composables/useCityStations'
import { useAnalysisStore } from '@/stores/analysis'
import { loadAMap } from '@/utils/amap'
import { escapeHtml, formatNumber } from '@/utils/format'
import { getPoiNameHints } from '@/utils/poiQuality'
import { classificationLabels, reviewStatusLabels } from '@/config/analysis'
import { useStationSearch } from '@/composables/useStationSearch'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps({
  cityCode: { type: String, required: true },
  districtCode: { type: String, default: '' },
  focusPosition: { type: Array, default: null },
  stationFilters: { type: Object, default: null },
})
const emit = defineEmits(['district-select', 'analysis-select', 'station-select'])
const route = useRoute()
const router = useRouter()
const analysis = useAnalysisStore()
const stationScope = computed(() => props.stationFilters || analysis)
const district = computed(() =>
  analysis.districtCatalog.find(
    (row) => row.code === props.districtCode && row.cityCode === props.cityCode,
  ),
)
const city = computed(() => cityMapConfig[props.cityCode])
const wrapper = ref(null)
const canvas = ref(null)
const layer = ref('cluster')
const cityBoundaryVisible = ref(true)
const districtVisible = ref(Boolean(props.districtCode))
const viewportOnly = ref(false)
const mapReady = ref(false)
const cameraStatus = ref('')
const mapError = ref('')
const districtLoading = ref(false)
const districtProgress = ref('')
const districtError = ref('')
const districtCount = ref(0)
const { stations, loading, error, total, loadedCount, load, cancel } = useCityStations()
const stationCount = computed(() => stations.value.length)
const markerLimit = 500
const searchText = ref('')
const searchOpen = ref(false)
const searchCurrentScope = ref(false)
const remoteSearch = useStationSearch()
const searchResult = computed(() => ({
  total: remoteSearch.total.value,
  items: remoteSearch.items.value,
}))
function runSearch(page = 1, immediate = false) {
  return remoteSearch.search(
    searchText.value,
    {
      city: searchCurrentScope.value ? props.cityCode : undefined,
      adcode: searchCurrentScope.value ? props.districtCode || undefined : undefined,
      classification: stationScope.value.classification || undefined,
      review_status: stationScope.value.reviewStatus || undefined,
      needs_review: stationScope.value.needsReview || undefined,
      batch: stationScope.value.batch || undefined,
    },
    page,
    immediate,
  )
}
watch([searchText, searchCurrentScope], () => runSearch())
function chooseSearchStation(station) {
  emit('station-select', station)
  if (
    station.cityCode !== props.cityCode ||
    (props.districtCode && station.adcode !== props.districtCode)
  ) {
    return
  }
  focusStation(station)
}
function clearSearch() {
  searchText.value = ''
  searchOpen.value = false
}
function focusStation(station) {
  if (!mapReady.value || !map) return
  selectedMarker?.setContent(markerContent())
  selectedMarker = null
  selectedStation = station
  searchOpen.value = false
  // Search is an explicit navigation action, including results outside the old bbox.
  // The debounced moveend handler reloads the new viewport when that mode is active.
  map.setZoomAndCenter(Math.max(map.getZoom(), 16), station.position, true)
  showStation(station)
}
const status = computed(() =>
  loading.value
    ? `正在加载样本 ${formatNumber(loadedCount.value)}${Number.isFinite(total.value) ? ` / ${formatNumber(total.value)}` : ''}`
    : `${district.value?.name || (viewportOnly.value ? '当前视野' : '当前市州')} · ${formatNumber(stationCount.value)} 条POI样本`,
)
let AMap, map, cluster, heatmap, popup, resizeObserver
let markers = []
let clusterStations = new Map()
let selectedMarker
let selectedStation
let cityPolygons = []
let districtPolygons = []
let disposed = false
let boundaryVersion = 0
let viewportTimer
let lastFocusedRequest = ''
let activeCameraKey = ''
const scopeCameraKey = () => `${props.cityCode}:${props.districtCode}`
function rememberCamera() {
  if (!map) return
  const center = map.getCenter()
  cameraStatus.value = `级别 ${map.getZoom().toFixed(1)} · 中心 ${center.getLng().toFixed(5)}, ${center.getLat().toFixed(5)} · GCJ-02`
  if (!activeCameraKey || districtLoading.value) return
  const districtCode = activeCameraKey.split(':')[1]
  if (
    districtCode &&
    !districtPolygons.some((polygon) => districtPolygonCodes.get(polygon) === districtCode)
  )
    return
  cameraCache.delete(activeCameraKey)
  cameraCache.set(activeCameraKey, {
    center: [center.getLng(), center.getLat()],
    zoom: map.getZoom(),
  })
  if (cameraCache.size > 32) cameraCache.delete(cameraCache.keys().next().value)
}
function restoreCamera() {
  // An explicit analysis location owns the initial camera. Do not start a
  // city fit animation that can finish after the point-selection watcher.
  const position = props.focusPosition
  if (map && !route.query.station && position?.length === 2 && position.every(Number.isFinite)) {
    map.setZoomAndCenter(12, position, true)
    return
  }
  const saved = cameraCache.get(activeCameraKey)
  if (saved && map) map.setZoomAndCenter(saved.zoom, saved.center, false, 450)
  else reset()
}
const markerStations = new WeakMap()
const markerClusterCounts = new WeakMap()
const boundMarkers = new WeakSet()
const districtPolygonCodes = new WeakMap()

function pointKey(point) {
  const coordinates = Array.isArray(point) ? point : [point.getLng(), point.getLat()]
  return coordinates.map((coordinate) => Number(coordinate).toFixed(7)).join(',')
}

function stationContent(station) {
  const hints = getPoiNameHints(station.name)
  const hintContent = hints.length
    ? `<p class="cm-review-hint">名称线索：${hints.map((hint) => escapeHtml(hint.label)).join(' / ')}（待核验）</p>`
    : ''
  const collectedAt = station.collectedAt
    ? new Date(station.collectedAt).toLocaleString('zh-CN', { hour12: false })
    : '—'
  return `<div class="cm-info-content">
    <strong>${escapeHtml(station.name)}</strong>
    <p>${escapeHtml(station.address || station.district)}</p>
    <div class="cm-info-tags"><span>${escapeHtml(classificationLabels[station.classification] || '待分类')}</span><span>${escapeHtml(reviewStatusLabels[station.reviewStatus] || '未核验')}</span></div>
    ${hintContent}
    ${station.completenessWarning ? '<p class="cm-review-hint">检索触及上限，区县样本可能不完整</p>' : ''}
    <details class="cm-info-details"><summary>数据来源与详情</summary><dl>
      <div><dt>来源</dt><dd>高德开放平台 · 入库POI样本</dd></div>
      <div><dt>采集时间</dt><dd>${escapeHtml(collectedAt)}</dd></div>
      <div><dt>POI ID</dt><dd>${escapeHtml(station.poiId || '—')}</dd></div>
      <div><dt>坐标</dt><dd>${station.position.map((value) => value.toFixed(6)).join(', ')} · GCJ-02</dd></div>
      <div><dt>质量批次</dt><dd>${escapeHtml(station.batch || '—')}</dd></div>
    </dl></details>
    <small>高德POI样本 · 非官方设施统计 · 营业状态待核验</small>
  </div>`
}
function markerContent(selected = false) {
  return `<span class="cm-poi-marker${selected ? ' is-selected' : ''}" aria-hidden="true"><svg width="10" height="12" viewBox="0 0 24 24"><path d="M13 2 4 14h7l-1 8 10-13h-7z" fill="currentColor"/></svg></span>`
}

function showStation(station) {
  if (!map || !station) return
  popup.setContent(stationContent(station))
  popup.open(map, station.position)
}

function bindMarkerEvents(marker) {
  if (boundMarkers.has(marker)) return
  boundMarkers.add(marker)
  marker.on('mouseover', () => {
    if (!selectedStation) showStation(markerStations.get(marker))
  })
  marker.on('click', () => {
    const station = markerStations.get(marker)
    if (station) {
      selectedMarker?.setContent(markerContent())
      selectedMarker = marker
      selectedStation = station
      marker.setContent(markerContent(true))
      if (!viewportOnly.value) map.setZoomAndCenter(map.getZoom(), station.position, true)
      showStation(station)
      emit('station-select', station)
    } else if (map && markerClusterCounts.get(marker) > 1) {
      popup.close()
      map.setZoomAndCenter(Math.min(map.getZoom() + 2, 18), marker.getPosition())
    }
  })
}

function bindStationMarker(marker, station) {
  markerStations.set(marker, station)
  markerClusterCounts.delete(marker)
  marker.setTitle(station.name)
  bindMarkerEvents(marker)
}

function clearStationLayers() {
  selectedMarker = null
  selectedStation = null
  popup?.close()
  cluster?.setMap(null)
  cluster = null
  heatmap?.setMap(null)
  heatmap = null
  if (markers.length) map?.remove(markers)
  markers = []
}

function renderStations() {
  if (!map || !mapReady.value) return
  // Update the active overlay in place after a viewport response. Its callbacks
  // read the current lookup, so reused markers never retain an old station.
  if (layer.value === 'cluster' && cluster && stations.value.length) {
    clusterStations = new Map(
      stations.value.map((station) => [pointKey(station.position), station]),
    )
    cluster.setData(stations.value.map((station) => ({ lnglat: station.position })))
    return
  }
  if (layer.value === 'heatmap' && heatmap && stations.value.length) {
    heatmap.setDataSet({
      data: stations.value.map((station) => ({
        lng: station.position[0],
        lat: station.position[1],
        count: 1,
      })),
    })
    return
  }
  clearStationLayers()
  if (!stations.value.length) return
  if (layer.value === 'heatmap') {
    heatmap = new AMap.HeatMap(map, {
      radius: 28,
      opacity: [0, 0.7],
      gradient: { 0.25: '#d8eec8', 0.5: '#80c98d', 0.75: '#2f956e', 1: '#125743' },
    })
    heatmap.setDataSet({
      data: stations.value.map((station) => ({
        lng: station.position[0],
        lat: station.position[1],
        count: 1,
      })),
    })
    return
  }
  if (layer.value === 'markers' && stationCount.value > markerLimit) {
    layer.value = 'cluster'
    return
  }
  if (layer.value === 'markers') {
    markers = stations.value.map((station) => {
      const marker = new AMap.Marker({
        position: station.position,
        content: markerContent(),
        anchor: 'center',
        zIndex: 130,
      })
      bindStationMarker(marker, station)
      return marker
    })
    map.add(markers)
    return
  }
  clusterStations = new Map(stations.value.map((station) => [pointKey(station.position), station]))
  cluster = new AMap.MarkerCluster(
    map,
    stations.value.map((station) => ({ lnglat: station.position })),
    {
      gridSize: 58,
      maxZoom: 17,
      renderClusterMarker: ({ marker, count }) => {
        const size = count >= 100 ? 46 : count >= 10 ? 39 : 32
        marker.setContent(
          `<span class="cm-cluster" style="width:${size}px;height:${size}px" title="${count}条POI样本 · 点击放大">${count}</span>`,
        )
        marker.setOffset(new AMap.Pixel(-size / 2, -size / 2))
        markerStations.delete(marker)
        markerClusterCounts.set(marker, count)
        marker.setTitle(`${count}条POI样本 · 点击放大`)
        bindMarkerEvents(marker)
      },
      renderMarker: ({ marker }) => {
        marker.setContent(markerContent())
        marker.setOffset(new AMap.Pixel(-11, -11))
        const station = clusterStations.get(pointKey(marker.getPosition()))
        if (station) bindStationMarker(marker, station)
      },
    },
  )
}

function removeDistricts() {
  if (districtPolygons.length) map?.remove(districtPolygons)
  districtPolygons = []
  districtCount.value = 0
}

function drawCity() {
  if (!map || !city.value) return
  if (cityPolygons.length) map.remove(cityPolygons)
  cityPolygons = []
  const geometry = city.value.feature.geometry
  const groups = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates]
  for (const paths of groups) {
    const polygon = new AMap.Polygon({
      path: paths,
      strokeColor: '#23725a',
      strokeWeight: 2,
      strokeOpacity: 0.9,
      fillColor: '#8ebeaa',
      fillOpacity: 0.04,
      bubble: true,
      zIndex: 35,
    })
    cityPolygons.push(polygon)
  }
  if (cityBoundaryVisible.value) map.add(cityPolygons)
}

function reset() {
  if (!map || !city.value) return
  const selectedPolygons = districtPolygons.filter(
    (polygon) => districtPolygonCodes.get(polygon) === props.districtCode,
  )
  if (selectedPolygons.length) {
    map.setFitView(selectedPolygons, false, [45, 55, 45, 55], 14)
    return
  }
  if (cityPolygons.length) map.setFitView(cityPolygons, false, [45, 55, 45, 55], 12)
  else map.setZoomAndCenter(10, city.value.center)
}

function currentBounds() {
  const bounds = map?.getBounds()
  if (!bounds) return undefined
  const southWest = bounds.getSouthWest()
  const northEast = bounds.getNorthEast()
  return [southWest.getLng(), southWest.getLat(), northEast.getLng(), northEast.getLat()]
    .map((coordinate) => coordinate.toFixed(6))
    .join(',')
}

function reloadStations() {
  if (viewportOnly.value && !mapReady.value) return
  return load(
    props.cityCode,
    viewportOnly.value ? currentBounds() : undefined,
    props.districtCode,
    {
      classification: stationScope.value.classification || undefined,
      review_status: stationScope.value.reviewStatus || undefined,
      needs_review: stationScope.value.needsReview || undefined,
      batch: stationScope.value.batch || undefined,
    },
  )
}

function onMoveEnd() {
  rememberCamera()
  if (!viewportOnly.value || disposed) return
  clearTimeout(viewportTimer)
  viewportTimer = setTimeout(reloadStations, 450)
}
function clearSelection() {
  selectedMarker?.setContent(markerContent())
  selectedMarker = null
  selectedStation = null
  popup?.close()
}
function clearMapSelection() {
  clearSelection()
  if (typeof route.query.station !== 'string') return
  analysis.selectedStation = null
  const query = { ...route.query }
  delete query.station
  router.replace({ path: route.path, query })
}

function queryDistrict(code, level, subdistrict, extensions) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('高德行政区边界请求超时')), 15000)
    const search = new AMap.DistrictSearch({ level, subdistrict, extensions, showbiz: false })
    search.search(code, (status, result) => {
      clearTimeout(timer)
      const match = result?.districtList?.find((district) => String(district.adcode) === code)
      if (status !== 'complete' || !match) {
        reject(new Error('高德行政区边界暂不可用，请稍后重试'))
        return
      }
      resolve(match)
    })
  })
}

async function loadDistrictBoundaries() {
  const version = ++boundaryVersion
  const code = props.cityCode
  removeDistricts()
  districtError.value = ''
  districtLoading.value = false
  if (!districtVisible.value || !mapReady.value || !city.value) return
  districtLoading.value = true
  try {
    const cacheKey = `${analysis.snapshot?.metadata.boundaryHash || 'provider'}:${code}`
    let districts = districtBoundaryCache.get(cacheKey)
    if (!districts && analysis.snapshot) {
      districtProgress.value = '读取已验证的区县边界'
      const boundaries = await analysis.boundaries(code)
      districts = boundaries.features.map((feature) => ({
        code: String(feature.properties.adcode),
        name: feature.properties.name,
        source: '真实行政边界快照',
        paths:
          feature.geometry.type === 'MultiPolygon'
            ? feature.geometry.coordinates
            : [feature.geometry.coordinates],
      }))
      if (!districts.length) throw new Error('当前市州尚无区县边界')
      districtBoundaryCache.set(cacheKey, districts)
    }
    if (!districts) {
      districtProgress.value = '查询区县目录'
      const cityResult = await queryDistrict(code, 'city', 1, 'base')
      if (disposed || version !== boundaryVersion) return
      const children = (cityResult.districtList || []).filter(
        (district) =>
          district.level === 'district' &&
          /^\d{6}$/.test(String(district.adcode)) &&
          String(district.adcode).startsWith(code.slice(0, 4)),
      )
      if (!children.length || children.length > 32)
        throw new Error('高德返回的区县目录不符合当前市州')
      districts = []
      for (const [index, child] of children.entries()) {
        if (disposed || version !== boundaryVersion) return
        districtProgress.value = `加载区县边界 ${index + 1} / ${children.length}`
        // At most one provider boundary request is active; only the selected city is queried.
        await new Promise((resolve) => setTimeout(resolve, 400))
        if (disposed || version !== boundaryVersion) return
        const district = await queryDistrict(String(child.adcode), 'district', 0, 'all')
        if (!district.boundaries?.length) throw new Error(`${child.name}边界暂不可用`)
        districts.push({
          code: String(child.adcode),
          name: child.name,
          source: '高德行政区边界',
          paths: district.boundaries,
        })
      }
      districtBoundaryCache.set(cacheKey, districts)
    }
    if (disposed || version !== boundaryVersion) return
    for (const district of districts) {
      for (const path of district.paths) {
        const polygon = new AMap.Polygon({
          path,
          strokeColor: '#377d68',
          strokeWeight: 1.3,
          strokeStyle: 'dashed',
          fillColor: '#accfbc',
          fillOpacity: 0.03,
          bubble: true,
          zIndex: 45,
        })
        polygon.on('mouseover', () => {
          polygon.setOptions({ fillOpacity: 0.2, strokeWeight: 2 })
          if (selectedStation) return
          const metrics = analysis.districts.find((row) => row.code === district.code)
          popup.setContent(
            `<div class="cm-district-tip"><strong>${escapeHtml(district.name)}</strong><p>行政代码 ${district.code} · ${escapeHtml(district.source)}</p>${metrics ? `<p>POI样本：${formatNumber(metrics.count)} 条<br/>POI样本密度：${formatNumber(metrics.density, 3)} 条/km²<br/>1km直线样本覆盖率：${formatNumber(metrics.coveragePercent, 2)}%<br/>待复核线索：${formatNumber(metrics.reviewCount)} 条<br/>${escapeHtml(metrics.qualityStatus)}${metrics.completenessWarning ? '<br/><b>检索触及上限，样本可能不完整</b>' : ''}</p>` : '<p>分析快照待接入</p>'}<small>点击区县查看站点；样本指标非官方统计。</small></div>`,
          )
          popup.open(map, polygon.getBounds().getCenter())
        })
        polygon.on('mouseout', () => {
          polygon.setOptions({
            fillOpacity: district.code === props.districtCode ? 0.16 : 0.03,
            strokeWeight: 1.3,
          })
          if (!selectedStation) popup.close()
        })
        polygon.on('click', () => emit('district-select', district.code))
        districtPolygonCodes.set(polygon, district.code)
        if (district.code === props.districtCode)
          polygon.setOptions({ fillOpacity: 0.16, strokeWeight: 2 })
        districtPolygons.push(polygon)
      }
    }
    map.add(districtPolygons)
    districtCount.value = districts.length
    if (props.districtCode) restoreCamera()
  } catch (cause) {
    if (!disposed && version === boundaryVersion) districtError.value = cause.message
  } finally {
    if (!disposed && version === boundaryVersion) {
      districtLoading.value = false
      districtProgress.value = ''
    }
  }
}

async function initializeMap() {
  mapError.value = ''
  try {
    AMap = await loadAMap()
    if (disposed || !city.value) return
    await nextTick()
    if (disposed) return
    map = new AMap.Map(canvas.value, {
      center: city.value.center,
      zoom: 10,
      viewMode: '2D',
      dragEnable: true,
      jogEnable: false,
      scrollWheel: true,
      features: ['bg', 'road', 'point'],
      mapStyle: 'amap://styles/normal',
      resizeEnable: true,
    })
    popup = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -14), closeWhenClickMap: true })
    map.addControl(new AMap.Scale())
    map.on('moveend', onMoveEnd)
    map.on('zoomend', onMoveEnd)
    map.on('click', clearMapSelection)
    mapReady.value = true
    activeCameraKey = scopeCameraKey()
    drawCity()
    restoreCamera()
    renderStations()
    if (viewportOnly.value) reloadStations()
    if (districtVisible.value) loadDistrictBoundaries()
  } catch {
    if (!disposed) mapError.value = '高德地图加载失败，请检查网络与 JS API Key 配置后重试。'
  }
}

async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await wrapper.value.requestFullscreen()
  } catch {
    message.info('当前浏览器不支持全屏，可使用浏览器全屏模式')
  }
}

onMounted(() => {
  initializeMap()
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(wrapper.value)
})
watch(
  [
    () => props.cityCode,
    () => props.districtCode,
    () => stationScope.value.classification,
    () => stationScope.value.reviewStatus,
    () => stationScope.value.needsReview,
    () => stationScope.value.batch,
  ],
  () => {
    const nextCameraKey = scopeCameraKey()
    if (nextCameraKey !== activeCameraKey) {
      rememberCamera()
      activeCameraKey = nextCameraKey
    }
    ++boundaryVersion
    clearTimeout(viewportTimer)
    cancel()
    clearStationLayers()
    searchText.value = ''
    searchOpen.value = false
    remoteSearch.cancel()
    removeDistricts()
    districtError.value = ''
    districtLoading.value = false
    if (props.districtCode) districtVisible.value = true
    if (map) {
      drawCity()
      restoreCamera()
      if (districtVisible.value) loadDistrictBoundaries()
    }
    reloadStations()
  },
  { immediate: true },
)
watch([stations, layer], () => {
  const previousSelection = selectedStation
  const selectedPoi = previousSelection?.poiId
  renderStations()
  // A viewport reload or layer switch rebuilds markers, but should not dismiss
  // the explicitly selected station or recenter the camera a second time.
  if (selectedPoi && route.query.station === selectedPoi) {
    const station = stations.value.find((row) => row.poiId === selectedPoi)
    if (station || loading.value) {
      selectedStation = station || previousSelection
      showStation(selectedStation)
    }
  }
})
watch(cityBoundaryVisible, () => {
  if (!map) return
  if (cityBoundaryVisible.value) map.add(cityPolygons)
  else map.remove(cityPolygons)
})
watch(districtVisible, loadDistrictBoundaries)
watch([mapReady, loading, districtLoading, () => route.query.station], () => {
  if (typeof route.query.station !== 'string') {
    clearSelection()
    lastFocusedRequest = ''
    return
  }
  if (!mapReady.value || loading.value || districtLoading.value) return
  const station = stations.value.find((row) => row.poiId === route.query.station)
  const request = `${props.cityCode}:${props.districtCode}:${route.query.station}`
  if (station && request !== lastFocusedRequest) {
    lastFocusedRequest = request
    focusStation(station)
    wrapper.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
  }
})
let lastGridFocus = ''
watch(
  [
    mapReady,
    districtLoading,
    () => props.focusPosition,
    () => props.cityCode,
    () => props.districtCode,
  ],
  () => {
    const position = props.focusPosition
    if (!position) {
      lastGridFocus = ''
      return
    }
    if (
      !mapReady.value ||
      districtLoading.value ||
      !map ||
      route.query.station ||
      position.length !== 2 ||
      !position.every(Number.isFinite)
    )
      return
    const key = `${props.cityCode}:${props.districtCode}:${position.join(',')}`
    if (key === lastGridFocus) return
    lastGridFocus = key
    map.setZoomAndCenter(Math.max(map.getZoom(), 12), position, true)
  },
  { flush: 'post' },
)
watch(viewportOnly, () => {
  clearTimeout(viewportTimer)
  reloadStations()
})
onBeforeUnmount(() => {
  rememberCamera()
  disposed = true
  ++boundaryVersion
  clearTimeout(viewportTimer)
  resizeObserver?.disconnect()
  clearStationLayers()
  map?.off('moveend', onMoveEnd)
  map?.off('zoomend', onMoveEnd)
  map?.off('click', clearMapSelection)
  map?.destroy()
  map = null
})
defineExpose({
  refresh: reloadStations,
  setHeatmapData: () => {
    // Heatmap always uses the persisted POI coordinates with equal weights.
    layer.value = 'heatmap'
  },
  drillToDistrict: () => {
    districtVisible.value = true
  },
})
</script>

<template>
  <section ref="wrapper" class="city-map">
    <header class="cm-header">
      <div>
        <h2>{{ district?.name || city?.shortName }}真实站点地图</h2>
        <p>
          高德可检索POI样本 · GCJ-02<span v-if="stationFilters">
            · 独立口径：{{ classificationLabels[stationScope.classification] }}</span
          >
        </p>
      </div>
      <div class="cm-header-actions">
        <span class="cm-live-chip">高德 JS API 2.0</span
        ><button class="icon-button" aria-label="市州地图全屏" @click="fullscreen">
          <AppIcon name="expand" :size="17" />
        </button>
      </div>
    </header>
    <div class="cm-toolbar">
      <div class="cm-layer-switch" role="group" aria-label="站点展示图层">
        <button
          :class="{ active: layer === 'cluster' }"
          :aria-pressed="layer === 'cluster'"
          @click="layer = 'cluster'"
        >
          点聚合
        </button>
        <button
          :class="{ active: layer === 'markers' }"
          :aria-pressed="layer === 'markers'"
          :disabled="stationCount > markerLimit"
          :title="
            stationCount > markerLimit
              ? '请先选择区县或缩小当前视野，单独Marker最多显示500条'
              : '逐点显示当前样本'
          "
          @click="layer = 'markers'"
        >
          Marker
        </button>
        <button
          :class="{ active: layer === 'heatmap' }"
          :aria-pressed="layer === 'heatmap'"
          @click="layer = 'heatmap'"
        >
          POI样本聚集度
        </button>
      </div>
      <a-checkbox v-model:checked="cityBoundaryVisible">市州边界</a-checkbox>
      <a-checkbox v-model:checked="districtVisible">区县边界</a-checkbox>
      <a-checkbox v-model:checked="viewportOnly" :disabled="!mapReady">仅当前视野</a-checkbox>
      <span v-if="stationCount > markerLimit" class="cm-marker-limit"
        >样本较多，使用聚合；区县或视野内≤500条可逐点显示</span
      >
    </div>
    <div class="cm-search">
      <span class="cm-search-label">全库站点检索</span>
      <input
        aria-label="搜索入库站点"
        v-model="searchText"
        type="search"
        placeholder="输入站点名称、地址或POI ID"
        @input="searchOpen = true"
        @focus="searchOpen = true"
        @keydown.esc="searchOpen = false"
        @keydown.enter.prevent="searchResult.items[0] && chooseSearchStation(searchResult.items[0])"
      />
      <button v-if="searchText" type="button" @click="clearSearch">清除</button>
      <a-checkbox v-model:checked="searchCurrentScope">仅当前行政区</a-checkbox>
      <span v-if="searchText" role="status">{{
        remoteSearch.loading.value ? '检索中…' : `${searchResult.total} 条匹配`
      }}</span>
      <div v-if="searchOpen && searchText.trim()" class="cm-search-results">
        <button
          v-for="station in searchResult.items"
          :key="station.id"
          type="button"
          @click="chooseSearchStation(station)"
        >
          <strong>{{ station.name }}</strong
          ><small>{{ station.address || station.district }}</small>
        </button>
        <p v-if="remoteSearch.loading.value" role="status">正在检索入库样本…</p>
        <p v-else-if="remoteSearch.error.value" role="alert">
          {{ remoteSearch.error.value }} <button @click="runSearch(1, true)">重试</button>
        </p>
        <p v-else-if="!searchResult.total">没有匹配的入库站点，请调整名称或筛选条件。</p>
        <div v-if="searchResult.total > remoteSearch.pageSize" class="cm-search-pagination">
          <button
            :disabled="remoteSearch.loading.value || remoteSearch.page.value === 1"
            @click="runSearch(remoteSearch.page.value - 1, true)"
          >
            上一页
          </button>
          <span
            >第{{ remoteSearch.page.value }}页 /
            {{ Math.ceil(searchResult.total / remoteSearch.pageSize) }}页</span
          >
          <button
            :disabled="
              remoteSearch.loading.value ||
              remoteSearch.page.value * remoteSearch.pageSize >= searchResult.total
            "
            @click="runSearch(remoteSearch.page.value + 1, true)"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
    <div class="cm-map-body">
      <div
        ref="canvas"
        class="cm-canvas"
        role="img"
        :aria-label="`${district?.name || city?.name}高德地图，支持站点标记、点聚合、热力图与区县边界`"
      />
      <div
        v-if="mapError || !mapReady"
        class="cm-map-placeholder"
        :role="mapError ? 'alert' : 'status'"
      >
        <AppIcon name="map" :size="28" />
        <p>{{ mapError || '正在连接高德地图…' }}</p>
        <button v-if="mapError" @click="initializeMap">重试地图</button>
      </div>
      <div class="cm-status" aria-live="polite">
        <span :class="{ 'cm-status-dot': true, loading }" /><span>{{ status }}</span
        ><button :disabled="loading" @click="reloadStations">刷新</button>
      </div>
      <div
        v-if="error || districtError || districtLoading"
        class="cm-query-notice"
        :role="error || districtError ? 'alert' : 'status'"
      >
        <span>{{ error || districtError || districtProgress }}</span
        ><button v-if="error" @click="reloadStations">重新加载站点</button
        ><button v-else-if="districtError" @click="loadDistrictBoundaries">重试边界</button>
      </div>
      <div v-if="!loading && !error && mapReady && stationCount === 0" class="cm-empty-notice">
        {{
          viewportOnly
            ? '当前视野内暂无已入库POI样本'
            : districtCode
              ? '当前区县及筛选条件下暂无已入库POI样本'
              : '当前市州及筛选条件下暂无已入库POI样本'
        }}
      </div>
      <div class="cm-zoom">
        <button
          aria-label="放大市州地图"
          :disabled="!mapReady"
          @click="map.setZoom(map.getZoom() + 1)"
        >
          +</button
        ><button
          aria-label="缩小市州地图"
          :disabled="!mapReady"
          @click="map.setZoom(map.getZoom() - 1)"
        >
          −</button
        ><button aria-label="重置市州地图视角" :disabled="!mapReady" @click="reset">
          <AppIcon name="target" :size="17" />
        </button>
      </div>
      <div class="cm-layer-note">
        <template v-if="layer === 'heatmap'"
          ><span class="cm-heat-key" />低 → 高 · POI样本聚集度</template
        ><template v-else
          >点击{{
            layer === 'cluster' ? '聚合点放大，单点查看来源' : '站点查看来源与采集时间'
          }}</template
        ><span v-if="districtCount"> · {{ districtCount }}个区县边界</span>
      </div>
    </div>
    <footer class="cm-footer">
      <span v-if="cameraStatus" aria-label="地图视角">{{ cameraStatus }}</span>
      <span>{{
        layer === 'heatmap'
          ? '等权POI点热力，不作为设施密度或服务覆盖分析结果。'
          : '按当前市州或视野读取已入库样本，不代表官方设施总量。'
      }}</span>
      <div class="cm-reserved" aria-label="空间分析入口">
        <button @click="emit('analysis-select', 'coverage')">1km样本覆盖 ↘</button
        ><button @click="emit('analysis-select', 'accessibility')">5/10/15分钟道路观测 ↗</button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.cm-search {
  position: relative;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-3);
  border-bottom: 1px solid var(--border);
  font-size: var(--type-caption);
}
.cm-search input {
  flex: 1;
  min-width: 150px;
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  color: var(--text);
  background: var(--surface);
}
.cm-search button {
  min-height: 36px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--primary-dark);
  padding: 6px 10px;
  cursor: pointer;
}
.cm-search-results {
  position: absolute;
  top: 100%;
  left: var(--space-3);
  right: var(--space-3);
  max-height: 260px;
  overflow-y: auto;
  z-index: 200;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-overlay);
}
.cm-search-results button {
  width: 100%;
  display: grid;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  gap: 4px;
}
.cm-search-results button:hover {
  background: var(--primary-soft);
}
.cm-search-results small {
  color: var(--text-secondary);
}
.cm-search-results p {
  padding: var(--space-3);
  margin: 0;
  color: var(--text-secondary);
}
.cm-search-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2);
  border-top: 1px solid var(--border);
}
.cm-search-pagination button {
  width: auto;
  flex: 0 0 auto;
}
.cm-marker-limit {
  color: var(--text-secondary);
  font-size: var(--type-caption);
}
.city-map :deep(.cm-poi-marker.is-selected) {
  outline: 3px solid var(--primary-dark);
  outline-offset: 3px;
  transform: scale(1.2);
}
.city-map {
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  min-height: 560px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
}
.cm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px 12px;
}
.cm-header h2 {
  font-size: 18px;
  font-weight: 650;
  margin: 0 0 4px;
  color: var(--primary-dark);
}
.cm-header p {
  margin: 0;
  font-size: 12px;
  color: #62796d;
}
.cm-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.cm-live-chip {
  font-size: 11px;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.cm-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 15px;
  padding: 0 22px 14px;
  border-bottom: 1px solid var(--border);
}
.cm-layer-switch {
  display: flex;
  padding: 3px;
  border: 1px solid #d6e2da;
  border-radius: 6px;
  background: #f5f8f5;
}
.cm-layer-switch button {
  border: 0;
  background: transparent;
  color: #586f61;
  border-radius: 4px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}
.cm-layer-switch button.active {
  background: #fff;
  color: #19634e;
  box-shadow: 0 1px 4px #254c3214;
  font-weight: 600;
}
.cm-toolbar :deep(.ant-checkbox-wrapper) {
  margin: 0;
  font-size: 12px;
  color: #425a4d;
}
.cm-map-body {
  position: relative;
  flex: 1;
  min-height: 440px;
  background: #eef2eb;
}
.cm-canvas {
  position: absolute;
  inset: 0;
}
.cm-map-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  background: #f2f6f1;
  color: #5f7869;
  z-index: 2;
  padding: 25px;
  text-align: center;
}
.cm-map-placeholder p {
  font-size: 13px;
}
.cm-map-placeholder button,
.cm-status button,
.cm-query-notice button {
  border: 1px solid #d0dfd3;
  border-radius: 4px;
  background: #fff;
  color: #21705a;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}
.cm-status {
  position: absolute;
  left: 16px;
  top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ffffffed;
  box-shadow: 0 2px 10px #183a2712;
  border: 1px solid #dce6dd;
  border-radius: 6px;
  padding: 8px 11px;
  font-size: 12px;
  color: #345943;
  z-index: 3;
}
.cm-status-dot {
  width: 6px;
  height: 6px;
  background: #2b9373;
  border-radius: 50%;
}
.cm-status-dot.loading {
  background: #be9155;
}
.cm-query-notice {
  position: absolute;
  left: 16px;
  top: 65px;
  max-width: calc(100% - 32px);
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fffdf3ee;
  border: 1px solid #e4dbc0;
  border-radius: 5px;
  padding: 7px 10px;
  font-size: 12px;
  color: #775f35;
  z-index: 3;
}
.cm-empty-notice {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #fffef0ed;
  padding: 9px 13px;
  border-radius: 5px;
  font-size: 12px;
  color: #766748;
  pointer-events: none;
}
.cm-zoom {
  position: absolute;
  right: 16px;
  top: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #d7e2d8;
  border-radius: 5px;
  background: #fff;
  box-shadow: 0 2px 10px #183a2712;
}
.cm-zoom button {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 0;
  background: #fff;
  border-bottom: 1px solid #e7ece5;
  font-size: 21px;
  color: #476b57;
  cursor: pointer;
}
.cm-zoom button:last-child {
  border: 0;
}
.cm-zoom button:hover {
  background: #edf5ee;
}
.cm-layer-note {
  position: absolute;
  bottom: 28px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #d7e2d8;
  background: #fffffff0;
  padding: 5px 9px;
  border-radius: 4px;
  color: #4a6656;
  font-size: 11px;
  pointer-events: none;
}
.cm-heat-key {
  width: 52px;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(90deg, #d8eec8, #80c98d, #2f956e, #125743);
}
.cm-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 18px;
  padding: 9px 20px;
  color: #667d6c;
  background: #f9fbf7;
  border-top: 1px solid var(--border);
  font-size: 11px;
}
.cm-reserved {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #6d8072;
}
.cm-reserved small {
  background: #eef1ea;
  border-radius: 3px;
  padding: 0 4px;
  font-size: 10px;
}
.cm-reserved button {
  border: 1px solid #cbded1;
  border-radius: 4px;
  padding: 3px 7px;
  color: #17624f;
  background: #fff;
  font-size: 12px;
}
.city-map:fullscreen {
  width: 100vw;
  height: 100vh;
  border: 0;
  border-radius: 0;
}
.city-map :deep(.cm-poi-marker) {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2px solid #fff;
  color: #fff;
  background: #22795e;
  box-shadow: 0 1px 5px #163c404d;
}
.city-map :deep(.cm-cluster) {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2px solid #ffffffe8;
  color: #fff;
  background: #2a8064e8;
  box-shadow: 0 2px 9px #284d3b33;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}
.city-map :deep(.cm-info-content) {
  width: 280px;
  padding: 4px 2px;
  color: #2e4839;
  font-family: inherit;
}
.city-map :deep(.cm-info-content strong),
.city-map :deep(.cm-district-tip strong) {
  font-size: 14px;
  color: #1e604a;
}
.city-map :deep(.cm-info-content p) {
  margin: 5px 0 10px;
  color: #5c7164;
  font-size: 12px;
  line-height: 1.6;
}
.city-map :deep(.cm-info-tags) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.city-map :deep(.cm-info-tags span) {
  padding: 3px 8px;
  border-radius: 4px;
  background: #edf4ef;
  color: #3f6251;
  font-size: 12px;
}
.city-map :deep(.cm-info-details) {
  border-top: 1px solid #e3eae1;
  padding-top: 9px;
}
.city-map :deep(.cm-info-details summary) {
  cursor: pointer;
  color: #1e604a;
  font-size: 12px;
  padding: 2px 0;
}
.city-map :deep(.cm-info-details summary:focus-visible) {
  outline: 2px solid #258368;
  outline-offset: 3px;
}
.city-map :deep(.cm-info-details[open] dl) {
  margin-top: 8px;
}
.city-map :deep(.cm-info-content dl) {
  margin: 0;
}
.city-map :deep(.cm-info-content .cm-review-hint) {
  padding: 8px;
  background: #faf4e8;
  border-left: 2px solid #b99659;
  color: #735b31;
}
.city-map :deep(.cm-info-content dl div) {
  display: flex;
  gap: 8px;
  margin: 4px 0;
  font-size: 11px;
}
.city-map :deep(.cm-info-content dt) {
  flex: 0 0 52px;
  color: #6c8073;
}
.city-map :deep(.cm-info-content dd) {
  margin: 0;
  overflow-wrap: anywhere;
}
.city-map :deep(.cm-info-content small) {
  display: block;
  margin-top: 8px;
  border-top: 1px solid #e3eae1;
  padding-top: 7px;
  color: #6b7e70;
  font-size: 10px;
}
.city-map :deep(.cm-district-tip p) {
  margin: 5px 0 0;
  font-size: 11px;
  color: #5c7164;
}
@media (max-width: 1100px) {
  .cm-header {
    padding: 15px 16px 11px;
  }
  .cm-toolbar {
    padding: 0 16px 12px;
    gap: 10px;
  }
  .cm-live-chip {
    display: none;
  }
  .cm-status {
    left: 12px;
    top: 12px;
  }
  .cm-map-body {
    min-height: 420px;
  }
  .cm-layer-note {
    max-width: calc(100% - 100px);
    font-size: 10px;
  }
}
</style>
