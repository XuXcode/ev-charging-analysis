<script>
const spatialCameraCache = new Map()
</script>
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts/core'
import { bindMapDrag } from '@/utils/map-drag'
import { cityLabelStyle, cityLabelFormatter } from '@/utils/map-label'
import { bindProvinceOutline } from '@/utils/map-outline'
import { mapViewport, observeMapViewport, mapLegend } from '@/utils/map-viewport'
import { LinesChart, MapChart } from 'echarts/charts'
import { LabelLayout } from 'echarts/features'
import { TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { getAnalysisLayer } from '@/api/analysis'
import { regionTooltip, gridTooltip, lisaTooltip, regionTooltipStyle } from '@/utils/map-tooltip'
import {
  labeledHunan,
  cityMapConfig,
  MAP_COLORS,
  mapColorScale,
  mapHoverColor,
  mapLabelColor,
} from '@/config/maps'
import AppIcon from '@/components/AppIcon.vue'
import { chartTheme, themeName, mapPalette } from '@/utils/chart-theme'
import { exportChartPng, exportChartCsv } from '@/utils/export'
import { snapshotProvenance } from '@/utils/analysis-provenance'
import { cityAnalysisRoute } from '@/utils/analysis-filters'

echarts.use([
  LabelLayout,
  LinesChart,
  MapChart,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])
echarts.registerTheme(themeName, chartTheme)
// Fixed LISA classes. Numbers match the API's lisaCode, so legend and cells cannot drift.
const LISA_PIECES = [
  { value: 1, key: 'HH', label: 'HH 高—高', color: '#b4372e' },
  { value: 2, key: 'LL', label: 'LL 低—低', color: '#2b5f8a' },
  { value: 3, key: 'HL', label: 'HL 高—低', color: '#c98a2b' },
  { value: 4, key: 'LH', label: 'LH 低—高', color: '#4f9aa0' },
  { value: 5, key: 'NS', label: '不显著', color: '#ccd8d1' },
]
const LISA_COLOR = Object.fromEntries(LISA_PIECES.map((piece) => [piece.value, piece.color]))
const exporting = ref(false),
  exportError = ref('')
const props = defineProps({
  parentCode: { type: String, default: '430000' },
  selectionOnly: Boolean,
  compact: Boolean,
  layers: Boolean,
  initialLayer: { type: String, default: 'regions' },
  focusCode: { type: String, default: '' },
  scopeCode: { type: String, default: '' },
})
const emit = defineEmits(['city-select', 'district-select'])
const analysis = useAnalysisStore()
const dashboard = useDashboardStore()
const router = useRouter()
const root = ref(null),
  canvas = ref(null),
  layer = ref(props.initialLayer),
  error = ref(''),
  loading = ref(false)
const mapData = ref(null)
const boundaryData = ref(null)
const lisaStats = ref(null)
const gridDensityScale = computed(() => {
  if (layer.value !== 'grid' && layer.value !== 'hotspots') return null
  const densities = (mapData.value?.features || [])
    .map((feature) => feature.properties?.density)
    .filter((value) => Number.isFinite(value) && value >= 0)
  return mapColorScale(densities, (value) => number(value, 'density'))
})
const regions = computed(() =>
  props.parentCode === '430000'
    ? analysis.cities
    : analysis.districts.filter((row) => row.cityCode === props.parentCode),
)
const definition = computed(() =>
  layer.value === 'grid' || layer.value === 'hotspots'
    ? { label: '网格POI样本密度', unit: '条/km²', key: 'density' }
    : layer.value === 'lisa'
      ? { label: 'LISA局部空间关联', unit: '', key: 'lisaCode' }
      : layer.value === 'coverage'
        ? { label: '1km样本覆盖率', unit: '%', key: 'coveragePercent' }
        : layer.value === 'uncovered'
          ? { label: '样本未覆盖面积', unit: 'km²', key: 'uncoveredAreaKm2' }
          : analysis.definition,
)
const title = computed(() =>
  layer.value === 'regions'
    ? `${props.parentCode === '430000' ? '湖南省' : '区县'}${definition.value?.label || 'POI样本分布'}`
    : {
        grid: '5km网格POI样本密度',
        hotspots: 'POI样本聚集分布',
        lisa: "LISA空间关联（Moran's I）",
        coverage: '1km直线样本覆盖',
        uncovered: '样本未覆盖区域',
      }[layer.value],
)
const warning = computed(() => regions.value.some((row) => row.completenessWarning))
const number = (value, key = definition.value?.key) =>
  Number.isFinite(value)
    ? value.toLocaleString('zh-CN', {
        maximumFractionDigits: key === 'count' ? 0 : key === 'density' ? 3 : 2,
      })
    : '—'
const fixed = (value, digits = 2) => (Number.isFinite(value) ? Number(value).toFixed(digits) : '—')
let chart,
  removeMapDrag,
  removeOutline,
  observer,
  abort,
  generation = 0,
  zoom = 1,
  center
let activeCameraKey = ''
const cameraKey = () => `${props.parentCode}:${props.scopeCode}:${layer.value}`
function rememberCamera() {
  if (!activeCameraKey) return
  spatialCameraCache.set(activeCameraKey, { zoom, center: center ? [...center] : undefined })
  if (spatialCameraCache.size > 32)
    spatialCameraCache.delete(spatialCameraCache.keys().next().value)
}
function restoreCamera() {
  const saved = spatialCameraCache.get(activeCameraKey)
  zoom = saved?.zoom || 1
  center = saved?.center ? [...saved.center] : undefined
}
// ECharts syncs roam back into the parsed model option, so the live camera can be
// read from the model. `chart.getOption()` would deep-clone every datum (8895 grid
// cells) and used to run on each roam frame, which was the main drag bottleneck.
function readCamera() {
  const model = chart?.getModel?.()
  const target =
    layer.value === 'regions' ? model?.getSeriesByIndex?.(0) : model?.getComponent?.('geo', 0)
  if (!target?.get) return null
  const nextZoom = target.get('zoom')
  if (!Number.isFinite(nextZoom)) return null
  const nextCenter = target.get('center')
  return { zoom: nextZoom, center: Array.isArray(nextCenter) ? [...nextCenter] : undefined }
}
const mapName = `sample-analysis-${Math.random().toString(36).slice(2)}`

function featureRows() {
  return (mapData.value?.features || [])
    .filter(
      (f) =>
        ['Polygon', 'MultiPolygon'].includes(f.geometry?.type) && f.geometry.coordinates.length,
    )
    .map((feature) => {
      const code = String(
        feature.properties.adcode || feature.properties.code || feature.properties.id,
      )
      const region =
        regions.value.find((row) => row.code === code) ||
        analysis.districts.find((row) => row.code === code)
      const data = region || feature.properties
      return { feature, code, name: data.name || code, value: data[definition.value?.key], data }
    })
}
function tooltip(row) {
  if (!row) return ''
  if (layer.value === 'lisa') {
    return lisaTooltip({
      id: row.code,
      count: row.data.count,
      areaKm2: row.data.areaKm2,
      density: row.data.density,
      lisaClass: row.data.lisaClass,
      lisaClassLabel: row.data.lisaClassLabel,
      localI: row.data.localI,
      pSim: row.data.pSim,
      qFdr: row.data.qFdr,
      significant: row.data.significant,
      rawSignificant: row.data.rawSignificant,
    })
  }
  const grid = layer.value === 'grid' || layer.value === 'hotspots'
  if (grid) {
    return gridTooltip({
      id: row.code,
      count: row.data.count,
      areaKm2: row.data.areaKm2,
      density: row.data.density,
      hotspot: row.data.hotspot,
    })
  }
  return regionTooltip({
    name: row.name,
    count: row.data.count,
    sharePercent: row.data.sharePercent,
    reviewCount: row.data.reviewCount,
    completenessWarning: row.data.completenessWarning,
  })
}

// Administrative boundaries become polylines on the same geo coordinate system as the
// grid, so they always pan and zoom together instead of rendering as a second map.
function boundaryPolylines(geojson) {
  const lines = []
  for (const feature of geojson?.features || []) {
    const geometry = feature.geometry
    if (!geometry) continue
    const polygons =
      geometry.type === 'Polygon'
        ? [geometry.coordinates]
        : geometry.type === 'MultiPolygon'
          ? geometry.coordinates
          : []
    for (const polygon of polygons) {
      for (const ring of polygon) {
        if (ring?.length > 1) lines.push({ coords: ring })
      }
    }
  }
  return lines
}

function render() {
  if (!chart || !mapData.value || !canvas.value?.clientWidth || !canvas.value?.clientHeight) return
  const rows = featureRows()
  if (!rows.length) {
    chart.clear()
    return
  }
  echarts.registerMap(mapName, {
    type: 'FeatureCollection',
    features: rows.map((row) => ({
      ...row.feature,
      properties: {
        ...row.feature.properties,
        name: row.code,
        ...(cityMapConfig[row.code]?.labelCenter
          ? { cp: cityMapConfig[row.code].labelCenter }
          : {}),
      },
    })),
  })
  const isGrid = layer.value === 'grid' || layer.value === 'hotspots'
  const isLisa = layer.value === 'lisa'
  const gridLike = isGrid || isLisa
  const isRegion = layer.value === 'regions'
  const classified = isRegion || layer.value === 'coverage' || isGrid || isLisa
  // For grid density use a province-wide fixed scale so colors mean the same density
  // regardless of which city or county is selected. LISA uses fixed class colours.
  const scale = isLisa
    ? { pieces: LISA_PIECES, color: (value) => LISA_COLOR[Number(value)] || LISA_COLOR[5] }
    : isGrid
      ? gridDensityScale.value
      : mapColorScale(
          regions.value.map((row) => row[definition.value?.key]),
          (value) => number(value),
        )
  const max = Math.max(0.001, ...rows.map((row) => row.value || 0))
  const selectedCode = props.focusCode || analysis.cityCode || dashboard.selectedCityCode
  const hasBoundaryOverlay = boundaryData.value && !isRegion
  const viewport = mapViewport(canvas.value, { features: rows.map((row) => row.feature) })
  const gridBaseColor = (row) => {
    if (!Number.isFinite(row.value)) return MAP_COLORS.empty
    return gridLike ? scale.color(row.value) : mapPalette[0]
  }
  const data = rows.map((row) => {
    const base = classified ? scale.color(row.value) : gridBaseColor(row)
    const selected = row.code === selectedCode
    const color = selected ? MAP_COLORS.selected : base
    const hover = selected ? color : mapHoverColor(base)
    return {
      name: row.code,
      code: row.code,
      value: row.value,
      sampleCount: row.data.count,
      regionName: cityMapConfig[row.code]?.shortName || row.name,
      ...(selected ? { itemStyle: { areaColor: color } } : {}),
      ...(Number.isFinite(row.value) ? {} : { itemStyle: { areaColor: MAP_COLORS.empty } }),
      label: { show: false },
      emphasis: { itemStyle: { areaColor: hover }, label: { show: false } },
    }
  })
  const mapSeries = {
    id: 'analysis-layer',
    type: 'map',
    map: mapName,
    data,
    itemStyle: {
      borderColor: gridLike ? '#7ba88f' : '#fff',
      borderWidth: gridLike ? 0.8 : 1.4,
      areaColor: gridLike ? MAP_COLORS.empty : '#f0f4ef',
    },
    emphasis: {
      itemStyle: {
        borderColor: MAP_COLORS.border,
        borderWidth: gridLike ? 1.2 : 2,
      },
    },
    select: { disabled: true },
  }
  if (isRegion) {
    // Region view keeps the internal geo and its labels.
    Object.assign(mapSeries, {
      roam: 'scale',
      zoomOnMouseWheel: true,
      moveOnMouseWheel: false,
      zoom,
      center,
      layoutCenter: ['50%', '50%'],
      layoutSize: '98%',
      ...viewport,
      aspectScale: 0.88,
      label: {
        show: !props.compact,
        ...cityLabelStyle,
        color: '#244b39',
        formatter: cityLabelFormatter,
      },
      labelLayout: { hideOverlap: true },
    })
  } else {
    // Grid/hotspot/coverage views bind to an explicit geo. The series and the
    // boundary polylines share geoIndex 0, so one roam state moves both layers.
    mapSeries.geoIndex = 0
  }
  const series = [mapSeries]
  if (hasBoundaryOverlay) {
    series.push({
      id: 'boundary-overlay',
      type: 'lines',
      coordinateSystem: 'geo',
      geoIndex: 0,
      polyline: true,
      silent: true,
      data: boundaryPolylines(boundaryData.value),
      lineStyle: { color: '#23725a', width: 1.8, opacity: 1 },
      z: 10,
    })
  }
  const option = {
    animation: false,
    tooltip: {
      trigger: 'item',
      confine: true,
      ...chartTheme.tooltip,
      ...regionTooltipStyle,
      formatter: (p) => tooltip(rows.find((row) => row.code === p.name)),
    },
    visualMap: {
      show: !props.compact,
      type: classified ? 'piecewise' : 'continuous',
      ...(classified
        ? {
            pieces: scale.pieces,
            seriesIndex: 0,
            outOfRange: { color: MAP_COLORS.empty },
            itemWidth: 18,
            itemHeight: 14,
            itemGap: 8,
          }
        : {}),
      ...(gridLike ? {} : { min: 0, max }),
      orient: 'horizontal',
      left: 20,
      bottom: 18,
      calculable: false,
      ...mapLegend(canvas.value),
      text: classified ? undefined : [`${number(max)} ${definition.value?.unit || ''}`, '0'],
      inRange: {
        color: layer.value === 'uncovered' ? ['#f5eddc', '#b18b4b'] : mapPalette,
      },
      textStyle: { color: '#435e50', fontSize: 12 },
    },
    series,
  }
  if (!isRegion) {
    option.geo = {
      map: mapName,
      roam: 'scale',
      zoomOnMouseWheel: true,
      moveOnMouseWheel: false,
      zoom,
      center,
      layoutCenter: ['50%', '50%'],
      layoutSize: '98%',
      ...viewport,
      aspectScale: 0.88,
      itemStyle: {
        areaColor: MAP_COLORS.empty,
        borderColor: gridLike ? '#7ba88f' : '#dbe5df',
        borderWidth: gridLike ? 0.8 : 1.2,
      },
      label: { show: false },
      emphasis: {
        itemStyle: { borderColor: MAP_COLORS.border, borderWidth: gridLike ? 1.4 : 1.8 },
        label: { show: false },
      },
      select: { disabled: true },
    }
  }
  chart.setOption(option, true)
  highlight()
}
function highlight() {
  if (!chart) return
  chart.dispatchAction({ type: 'downplay' })
  chart.dispatchAction({ type: 'hideTip' })
  // Grid cells use "x:y" ids; district focus highlighting only applies to region view.
  if (layer.value !== 'regions') return
  if (props.focusCode) {
    chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: props.focusCode })
    chart.dispatchAction({ type: 'showTip', seriesIndex: 0, name: props.focusCode })
    return
  }
  const code = dashboard.hoveredCityCode || dashboard.selectedCityCode
  if (code) chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: code })
  if (dashboard.hoveredCityCode && regions.value.some((row) => row.code === code))
    chart.dispatchAction({ type: 'showTip', seriesIndex: 0, name: code })
}
async function exportMap(format) {
  if (!chart || !mapData.value || loading.value || exporting.value) return
  exporting.value = true
  exportError.value = ''
  try {
    const meta = analysis.snapshot.metadata
    if (format === 'png')
      await exportChartPng(
        chart,
        title.value,
        `高德POI样本 · ${meta.algorithmVersion} · 非官方统计`,
        {
          ...snapshotProvenance(analysis.snapshot),
        },
      )
    else
      exportChartCsv(
        {
          series: [
            {
              name: definition.value.label,
              type: 'map',
              data: featureRows().map((r) => ({
                value: r.value,
                regionName: r.name,
                code: r.code,
                warning: r.data.completenessWarning,
              })),
            },
          ],
          yAxis: { name: definition.value.unit },
        },
        title.value,
        {
          ...snapshotProvenance(analysis.snapshot),
        },
      )
  } catch (failure) {
    exportError.value = failure.message
  } finally {
    exporting.value = false
  }
}
async function loadBoundaryOverlay() {
  if (layer.value === 'regions' || props.compact) {
    boundaryData.value = null
    return
  }
  if (props.parentCode === '430000') {
    boundaryData.value = labeledHunan
    return
  }
  try {
    boundaryData.value = await analysis.boundaries(props.parentCode)
  } catch {
    boundaryData.value = null
  }
}

async function load() {
  const current = ++generation
  abort?.abort()
  abort = new AbortController()
  loading.value = true
  mapData.value = null
  boundaryData.value = null
  lisaStats.value = null
  chart?.clear()
  error.value = ''
  try {
    const [data] = await Promise.all([
      layer.value === 'regions'
        ? analysis.boundaries(props.parentCode, abort.signal)
        : getAnalysisLayer(
            layer.value,
            {
              snapshot_id: analysis.snapshot.snapshotId,
              city: props.parentCode === '430000' ? undefined : props.parentCode,
              adcode: props.scopeCode || undefined,
            },
            abort.signal,
          ),
      loadBoundaryOverlay(),
    ])
    if (current !== generation) return
    mapData.value = data
    lisaStats.value = layer.value === 'lisa' ? data.statistics : null
    focusRegion()
    render()
  } catch (failure) {
    if (current === generation) error.value = failure.message
  } finally {
    if (current === generation) loading.value = false
  }
}
function focusRegion() {
  // A scoped county already has its own fitted geometry; doubling zoom clips its boundary.
  if (props.scopeCode && props.scopeCode === props.focusCode) {
    zoom = 1
    center = undefined
    return
  }
  if (!props.focusCode) return
  const row = featureRows().find((item) => item.code === props.focusCode)
  if (!row) return
  const points = []
  function visit(coordinates) {
    if (typeof coordinates[0] === 'number') points.push(coordinates)
    else coordinates.forEach(visit)
  }
  visit(row.feature.geometry.coordinates)
  if (!points.length) return
  const longitudes = points.map((p) => p[0]),
    latitudes = points.map((p) => p[1])
  center = [
    (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
    (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
  ]
  zoom = 2
}
watch(
  () => props.focusCode,
  () => {
    focusRegion()
    render()
  },
)
function reset() {
  zoom = 1
  center = undefined
  render()
}
function changeZoom(step) {
  zoom = Math.max(0.8, Math.min(5, zoom + step))
  render()
}
async function fullscreen() {
  if (document.fullscreenElement) await document.exitFullscreen()
  else await root.value.requestFullscreen().catch(() => {})
}
function select(code) {
  if (layer.value !== 'regions') return
  const row = regions.value.find((item) => item.code === code)
  if (!row) return
  if (row.level === 'district') {
    emit('district-select', code)
    if (!props.selectionOnly) router.push(cityAnalysisRoute(analysis, row.cityCode, code))
  } else if (props.selectionOnly) {
    dashboard.selectCity(code)
    emit('city-select', code)
  } else router.push(cityAnalysisRoute(analysis, code))
}
function resizeSpatialMap() {
  if (!chart || chart.isDisposed() || !canvas.value?.clientWidth || !canvas.value?.clientHeight)
    return
  chart.resize()
  const viewport = mapViewport(canvas.value)
  if (!viewport.layoutSize) return
  // Update the coordinate system that owns the current view, not a fixed series index.
  const target = layer.value === 'regions' ? { series: [viewport] } : { geo: [viewport] }
  chart.setOption({ ...target, visualMap: mapLegend(canvas.value) }, { lazyUpdate: true })
}

onMounted(() => {
  chart = echarts.init(canvas.value, themeName)
  removeMapDrag = bindMapDrag(chart, canvas.value, () =>
    layer.value === 'regions'
      ? { componentType: 'series', seriesIndex: 0 }
      : { componentType: 'geo', geoIndex: 0 },
  )
  removeOutline = bindProvinceOutline(
    chart,
    () => props.parentCode === '430000' && !props.scopeCode,
  )
  chart.on('click', (p) => select(p.name))
  chart.on('mouseover', (p) => {
    if (layer.value === 'regions') dashboard.hoverCity(p.name)
  })
  chart.on('globalout', () => dashboard.hoverCity(''))
  chart.on('georoam', () => {
    // Region view roams its internal series geo; grid/coverage views roam geo 0.
    const camera = readCamera()
    if (!camera) return
    zoom = camera.zoom
    center = camera.center
    rememberCamera()
  })
  observer = new ResizeObserver(resizeSpatialMap)
  observer.observe(canvas.value)
  observeMapViewport(observer, canvas.value)
  activeCameraKey = cameraKey()
  restoreCamera()
  load()
})
watch([() => props.parentCode, () => props.scopeCode, layer], () => {
  rememberCamera()
  activeCameraKey = cameraKey()
  restoreCamera()
  load()
})
watch(() => analysis.activeMetric, render)
watch(() => analysis.snapshot?.snapshotId, load)
watch(() => dashboard.hoveredCityCode, highlight)
watch(() => dashboard.selectedCityCode, render)
watch(() => analysis.cityCode, render)
onBeforeUnmount(() => {
  rememberCamera()
  ++generation
  abort?.abort()
  observer?.disconnect()
  removeOutline?.()
  removeMapDrag?.()
  chart?.dispose()
})
</script>
<template>
  <section ref="root" class="spatial-map" :class="{ compact }" :aria-label="title">
    <header>
      <div>
        <h2>{{ title }}</h2>
        <p v-if="!compact">
          真实POI样本 · 米制近似 · {{ analysis.snapshot?.metadata.algorithmVersion }}
        </p>
      </div>
      <div class="spatial-export-tools">
        <button
          v-if="!compact"
          aria-label="当前地图导出PNG"
          :disabled="loading || !!error || exporting || !mapData || !featureRows().length"
          @click="exportMap('png')"
        >
          PNG
        </button>
        <button
          v-if="!compact"
          aria-label="当前地图数据导出CSV"
          :disabled="loading || !!error || exporting || !mapData || !featureRows().length"
          @click="exportMap('csv')"
        >
          CSV
        </button>
        <button aria-label="分析地图全屏" @click="fullscreen">
          <AppIcon name="expand" :size="17" />
        </button>
      </div>
    </header>
    <div v-if="!compact" class="spatial-controls">
      <select v-if="layer === 'regions'" v-model="analysis.activeMetric" aria-label="地图分析指标">
        <option
          v-for="item in analysis.snapshot.indicatorDefinitions"
          :key="item.key"
          :value="item.key"
        >
          {{ item.label }}
        </option></select
      ><select v-if="layers" v-model="layer" aria-label="分析图层">
        <option value="regions">行政区指标</option>
        <option value="grid">5km网格样本密度</option>
        <option value="lisa">LISA空间关联</option>
        <option value="hotspots">描述性样本聚集分布</option>
        <option value="coverage">1km直线样本覆盖</option>
        <option value="uncovered">样本未覆盖区域</option>
      </select>
    </div>
    <div
      ref="canvas"
      class="spatial-canvas"
      role="img"
      :aria-label="`${title}，颜色表示${definition?.label}，可点击行政区钻取`"
    />
    <aside
      v-if="!compact && layer === 'lisa' && lisaStats"
      class="lisa-panel"
      aria-label="LISA空间自相关统计"
    >
      <div class="lisa-panel__head">
        <span>LISA 空间关联</span>
        <small>离线置换检验 · 全省口径</small>
      </div>
      <div class="lisa-panel__hero">
        <strong>{{ fixed(lisaStats.global?.moranI, 4) }}</strong>
        <span>全局 Moran's I</span>
        <em>p = {{ fixed(lisaStats.global?.pSim, 4) }}</em>
      </div>
      <dl class="lisa-panel__stats">
        <div>
          <dt>z 分数</dt>
          <dd>{{ fixed(lisaStats.global?.zScore, 2) }}</dd>
        </div>
        <div>
          <dt>FDR q&lt;0.05</dt>
          <dd>{{ lisaStats.significantCount }}<small>/ {{ lisaStats.cellCount }}</small></dd>
        </div>
        <div>
          <dt>未校正 p&lt;0.05</dt>
          <dd>{{ lisaStats.rawSignificantCount }}<small>个</small></dd>
        </div>
      </dl>
      <ul class="lisa-panel__classes">
        <li v-for="piece in LISA_PIECES" :key="piece.value">
          <i :style="{ background: piece.color }" />
          <span>{{ piece.label }}</span>
          <b>{{ lisaStats.classCounts?.[piece.key] ?? 0 }}</b>
        </li>
      </ul>
      <p class="lisa-panel__summary">{{ lisaStats.summary }}</p>
      <details class="lisa-panel__detail">
        <summary>口径与局限</summary>
        <p>{{ lisaStats.conclusion }}</p>
        <p>
          {{ lisaStats.weights?.type === 'queen' ? 'Queen' : 'Rook' }}邻接 · 行标准化 ·
          {{ lisaStats.permutations }} 次置换 · 零样本 {{ fixed(lisaStats.zeroSharePercent, 1) }}% ·
          计算 {{ fixed(lisaStats.seconds, 1) }}s
        </p>
      </details>
    </aside>
    <div v-if="loading || error" class="spatial-status" :role="error ? 'alert' : 'status'">
      {{ error || '读取分析快照图层…' }}<button v-if="error" @click="load">重试</button>
    </div>
    <p v-if="exportError" role="alert" class="spatial-export-error">{{ exportError }}</p>
    <div v-else-if="mapData && !featureRows().length" class="spatial-status" role="status">
      {{
        layer === 'hotspots'
          ? '当前范围没有达到全省P95阈值的聚集网格；不代表没有充电设施。'
          : '当前范围没有可显示的图层几何，请查看指标或切换范围。'
      }}
    </div>
    <div class="spatial-actions">
      <button aria-label="放大分析地图" @click="changeZoom(0.25)">+</button
      ><button aria-label="缩小分析地图" @click="changeZoom(-0.25)">−</button
      ><button aria-label="重置分析地图" @click="reset">↺</button>
    </div>
    <footer v-if="!compact">
      <span v-if="analysis.snapshot.stale">快照已过期，需重新计算 · </span
      ><span v-if="warning">部分区县检索触及上限，样本可能不完整 · </span
      >{{ number(analysis.snapshot.metadata.stationCount, 'count') }}条保留POI参与分析 ·
      {{
        analysis.needsReview
          ? '仅待复核线索 · 与所选类别取交集'
          : analysis.classification
            ? '已按POI类别筛选'
            : '包含疑似停业、专用、个人及未知样本'
      }}
      · 非官方覆盖率
      <span v-if="layer === 'grid' || layer === 'hotspots'">
        · 固定全省网格；选区展示相交完整网格，不重算局部密度</span
      >
      <span v-if="layer === 'lisa'"> · LISA为离线置换检验；空间显著不代表充电需求不足</span>
    </footer>
  </section>
</template>
<style scoped>
.spatial-export-tools {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.spatial-export-tools button {
  font-size: var(--type-caption);
  min-width: 36px;
}
.spatial-export-error {
  position: absolute;
  bottom: 55px;
  left: 20px;
  color: var(--danger);
  background: var(--danger-soft);
  padding: 8px;
}
.spatial-map {
  position: relative;
  background: #f6f9f5;
  border: 1px solid #dbe5df;
  border-radius: 8px;
  height: 100%;
  min-height: 530px;
  overflow: hidden;
}
.spatial-map:fullscreen {
  height: 100vh;
  min-height: 100vh;
}
header {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  padding: 20px 24px;
  display: flex;
  justify-content: space-between;
  z-index: 2;
  pointer-events: none;
}
header button {
  pointer-events: auto;
  background: white;
  border: 1px solid #dbe5df;
  border-radius: 5px;
  padding: 6px;
}
h2 {
  font-size: 18px;
  color: #243b35;
  margin: 0;
}
header p {
  font-size: 12px;
  color: #52685c;
  margin: 8px 0;
}
.spatial-controls {
  position: absolute;
  top: 88px;
  left: 24px;
  z-index: 2;
  display: flex;
  gap: 8px;
}
.spatial-controls select {
  background: #fff;
  border: 1px solid #dbe5df;
  color: #344c41;
  border-radius: 5px;
  padding: 7px 10px;
  font-size: 13px;
}
.spatial-canvas {
  position: absolute;
  inset: 112px 12px 58px;
}
.spatial-status {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #fff;
  padding: 16px;
  border: 1px solid #dbe5df;
  border-radius: 6px;
  color: #52685c;
}
.spatial-status button {
  margin-left: 12px;
  color: #17634e;
}
.spatial-actions {
  position: absolute;
  right: 18px;
  bottom: 100px;
  display: grid;
  border: 1px solid #dbe5df;
  border-radius: 5px;
  overflow: hidden;
}
.spatial-actions button {
  width: 32px;
  height: 32px;
  border: 0;
  background: #fff;
  color: #17634e;
}
.spatial-actions button + button {
  border-top: 1px solid #dbe5df;
}
footer {
  position: absolute;
  bottom: 0;
  width: 100%;
  padding: 12px 18px;
  font-size: 12px;
  line-height: 1.7;
  color: #52685c;
  background: #ffffffcf;
  border-top: 1px solid #dbe5df;
}
.compact {
  min-height: 0;
}
.compact header {
  padding: 16px;
}
.compact h2 {
  font-size: 14px;
}
.compact .spatial-canvas {
  inset: 60px 0 15px;
}
.compact .spatial-actions {
  bottom: 15px;
}
@media (max-width: 700px) {
  .spatial-controls {
    left: 16px;
    right: 16px;
    flex-wrap: wrap;
  }
  .spatial-map:not(.compact) {
    min-height: 600px;
  }
  .spatial-map:not(.compact) .spatial-canvas {
    top: 170px;
  }
  .lisa-panel {
    display: none;
  }
}

/* LISA statistics float: frosted glass, same material as the shared map overlays. */
.lisa-panel {
  position: absolute;
  /* Start below the HUD breadcrumb/filter strip instead of under it. */
  top: calc(var(--monitor-top-offset, 96px) + 8px);
  /* The HUD keeps a 368px right panel; sit inside the map, not under that panel. */
  right: calc(var(--monitor-right-offset, 36px) + 8px);
  z-index: 3;
  width: 274px;
  max-height: calc(100% - 176px);
  overflow-y: auto;
  padding: 14px 16px;
  display: grid;
  gap: 10px;
  color: #244b39;
  font-size: 12px;
  line-height: 1.5;
  border-radius: 14px;
  border: 1px solid rgba(24, 99, 74, 0.55);
  background: rgba(248, 252, 249, 0.88);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow:
    0 12px 30px rgba(25, 65, 45, 0.16),
    0 1px 0 rgba(255, 255, 255, 0.7) inset;
}
.lisa-panel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.lisa-panel__head span {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.lisa-panel__head small {
  font-size: 11px;
  color: #6b8577;
}
.lisa-panel__hero {
  display: grid;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(35, 114, 90, 0.07);
}
.lisa-panel__hero strong {
  font-size: 26px;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  color: #18634a;
}
.lisa-panel__hero span {
  font-size: 11px;
  color: #5d7568;
}
.lisa-panel__hero em {
  font-style: normal;
  font-size: 11px;
  color: #6b8577;
}
.lisa-panel__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}
.lisa-panel__stats div {
  display: grid;
  gap: 2px;
}
.lisa-panel__stats dt {
  font-size: 10.5px;
  color: #6b8577;
}
.lisa-panel__stats dd {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.lisa-panel__stats dd small {
  font-size: 10.5px;
  font-weight: 400;
  color: #7b9184;
}
.lisa-panel__classes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}
.lisa-panel__classes li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lisa-panel__classes i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex: none;
}
.lisa-panel__classes span {
  flex: 1;
  color: #3d5a4b;
}
.lisa-panel__classes b {
  font-variant-numeric: tabular-nums;
  color: #18634a;
}
.lisa-panel__summary {
  margin: 0;
  padding-top: 8px;
  border-top: 1px solid rgba(24, 99, 74, 0.14);
  font-size: 12px;
  color: #34503f;
}
.lisa-panel__detail summary {
  cursor: pointer;
  font-size: 11.5px;
  color: #18634a;
  font-weight: 600;
}
.lisa-panel__detail p {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: #5d7568;
}
</style>
