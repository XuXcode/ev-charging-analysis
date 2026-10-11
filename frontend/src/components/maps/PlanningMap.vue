<script setup>
/**
 * 需求代理评分规划参考地图（高德底图 + Loca.PolygonLayer 网格叠加）
 *
 * 以高德地图为底图，将 5km 需求代理评分网格叠加显示：
 * - 有分网格按评分连续着色（绿阶，高分深绿）
 * - 0 分网格在省域缩放级别浅底显示覆盖范围，放大后自动弱化淡出
 * - 点击区县排行可定位（真实行政边界叠加）
 * - 评分标注：需求代理评分，非建设决策依据；POI样本不代表官方总量。
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { usePlanningStore } from '@/stores/planning'
import { useAnalysisStore } from '@/stores/analysis'
import { loadAMap } from '@/utils/amap'
import { escapeHtml } from '@/utils/format'
import AppIcon from '@/components/AppIcon.vue'

const props = defineProps({
  parentCode: { type: String, default: '430000' },
  focusCode: { type: String, default: '' },
  scopeCode: { type: String, default: '' },
  compact: Boolean,
})
const emit = defineEmits(['district-select'])
const planning = usePlanningStore()
const analysis = useAnalysisStore()

const root = ref(null),
  canvas = ref(null),
  error = ref(''),
  loading = ref(false)
const mapData = ref(null)
const mode = ref('heatmap') // heatmap | grid

let AMap = null,
  Loca = null,
  map = null,
  loca = null,
  popup = null,
  resizeObserver = null,
  disposed = false,
  generation = 0,
  abort = null
let scoredLayer = null,
  zeroLayer = null,
  scoredSource = null,
  zeroSource = null,
  hoverPolygon = null,
  heatmap = null

// 评分配色（与全局 chart-theme 一致）
const palette = ['#eef5ec', '#c8dcc4', '#5eaa83', '#17634e']
const zeroColor = '#e0ebe0'
const zeroFillOpacity = 0.4
const zeroFadeZoom = 7 // 低到该级别后 0 分网格弱化淡出
const scoreFillOpacity = 0.82
// 热力图渐变（与网格配色一致：低分浅绿 → 高分深绿）
const heatGradient = {
  0.25: '#d9ecdc',
  0.45: '#8fc9a4',
  0.65: '#4fa07c',
  0.85: '#1d6e52',
  1: '#0e4a38',
}

const number = (value, digits = 2) =>
  Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: digits }) : '—'

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
}
function mix(hexA, hexB, t) {
  const a = hexToRgb(hexA),
    b = hexToRgb(hexB)
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}
function scoreColor(score, max) {
  if (!Number.isFinite(score) || score <= 0) return zeroColor
  const ratio = Math.max(0, Math.min(1, score / (max || 1)))
  if (ratio < 0.5) return mix(palette[0], palette[1], ratio / 0.5)
  if (ratio < 0.85) return mix(palette[1], palette[2], (ratio - 0.5) / 0.35)
  return mix(palette[2], palette[3], (ratio - 0.85) / 0.15)
}

function featureRows() {
  return (mapData.value?.features || [])
    .filter(
      (f) => ['Polygon', 'MultiPolygon'].includes(f.geometry?.type) && f.geometry.coordinates.length,
    )
    .map((feature) => {
      const p = feature.properties || {}
      return {
        feature,
        code: String(p.id || p.code || ''),
        value: Number(p.planningScore) || 0,
        demandWeighted: p.demandWeighted ?? 0,
        supplyCount: p.supplyCount ?? 0,
        areaKm2: p.areaKm2 ?? 0,
        demandDensity: p.demandDensity ?? 0,
      }
    })
}

function tooltip(row) {
  if (!row) return ''
  return `<div class="pm-tip"><strong>网格 ${escapeHtml(row.code)}</strong>
    <p>需求代理评分：<b>${number(row.value)} / 100</b><br/>
    加权需求POI：${number(row.demandWeighted, 1)} 条<br/>
    周边站点数：${number(row.supplyCount, 0)} 座<br/>
    网格面积：${number(row.areaKm2, 2)} km²</p>
    <small>需求代理评分 · 非建设决策依据 · POI样本不代表官方总量</small></div>`
}

/** 提取 GeoJSON geometry 的坐标点集合（计算边界框 / 定位用） */
function collectPoints(geometry, points) {
  if (!geometry) return
  if (geometry.type === 'Point') points.push(geometry.coordinates)
  else if (geometry.type === 'LineString') geometry.coordinates.forEach((c) => points.push(c))
  else if (geometry.type === 'Polygon') geometry.coordinates.forEach((ring) => ring.forEach((c) => points.push(c)))
  else if (geometry.type === 'MultiPolygon')
    geometry.coordinates.forEach((poly) => poly.forEach((ring) => ring.forEach((c) => points.push(c))))
  else if (geometry.type === 'MultiLineString')
    geometry.coordinates.forEach((line) => line.forEach((c) => points.push(c)))
  else if (geometry.type === 'GeometryCollection')
    geometry.geometries.forEach((g) => collectPoints(g, points))
}

/** GeoJSON geometry -> AMap path 数组 */
function toPaths(geometry) {
  const paths = []
  const push = (coords) => {
    if (coords?.[0]?.length >= 2 && typeof coords[0][0] === 'number') paths.push(coords)
    else coords?.forEach((c) => push(c))
  }
  push(geometry.coordinates)
  return paths
}

function gridBounds() {
  const points = []
  featureRows().forEach((r) => collectPoints(r.feature.geometry, points))
  if (!points.length) return null
  const lngs = points.map((p) => p[0]),
    lats = points.map((p) => p[1])
  return new AMap.Bounds(
    new AMap.LngLat(Math.min(...lngs), Math.min(...lats)),
    new AMap.LngLat(Math.max(...lngs), Math.max(...lats)),
  )
}

// ---------- 边界叠加 ----------
let cityBoundaryPolygons = []
let districtBoundaryPolygons = []

function clearBoundaries() {
  if (map) {
    map.remove(cityBoundaryPolygons)
    map.remove(districtBoundaryPolygons)
  }
  cityBoundaryPolygons = []
  districtBoundaryPolygons = []
}

/** 读取真实边界（市州级：430000 返回 14 市；市级返回区县）并叠加 */
async function drawBoundaries() {
  if (!map || disposed) return
  clearBoundaries()
  try {
    if (props.parentCode === '430000') {
      const fc = await analysis.boundaries('430000', abort?.signal)
      if (disposed) return
      for (const feature of fc.features || []) {
        for (const path of toPaths(feature.geometry)) {
          const polygon = new AMap.Polygon({
            path,
            strokeColor: '#23725a',
            strokeWeight: 1.6,
            strokeOpacity: 0.85,
            fillColor: '#8ebeaa',
            fillOpacity: 0.03,
            bubble: true,
            zIndex: 35,
          })
          cityBoundaryPolygons.push(polygon)
        }
      }
    } else {
      const city = await analysis.boundaries('430000', abort?.signal)
      if (disposed) return
      const cityFeature = city.features?.find(
        (f) => String(f.properties?.adcode) === props.parentCode,
      )
      if (cityFeature) {
        for (const path of toPaths(cityFeature.geometry)) {
          const polygon = new AMap.Polygon({
            path,
            strokeColor: '#23725a',
            strokeWeight: 2,
            strokeOpacity: 0.9,
            fillColor: '#8ebeaa',
            fillOpacity: 0.04,
            bubble: true,
            zIndex: 35,
          })
          cityBoundaryPolygons.push(polygon)
        }
      }
      const districts = await analysis.boundaries(props.parentCode, abort?.signal)
      if (disposed) return
      for (const feature of districts.features || []) {
        for (const path of toPaths(feature.geometry)) {
          const polygon = new AMap.Polygon({
            path,
            strokeColor: '#7aa893',
            strokeWeight: 1.2,
            strokeStyle: 'dashed',
            fillColor: '#accfbc',
            fillOpacity: 0.03,
            bubble: true,
            zIndex: 36,
          })
          districtBoundaryPolygons.push(polygon)
        }
      }
    }
    map.add([...cityBoundaryPolygons, ...districtBoundaryPolygons])
  } catch (cause) {
    if (!disposed) console.warn('[PlanningMap] 行政边界加载失败', cause)
  }
}

// ---------- 网格渲染 ----------
function clearGridLayers() {
  if (heatmap) {
    heatmap.setMap(null)
    heatmap = null
  }
  if (loca) {
    if (scoredLayer) {
      loca.remove(scoredLayer)
      scoredLayer.destroy()
      scoredLayer = null
    }
    if (zeroLayer) {
      loca.remove(zeroLayer)
      zeroLayer.destroy()
      zeroLayer = null
    }
  }
  scoredSource?.destroy()
  scoredSource = null
  zeroSource?.destroy()
  zeroSource = null
  if (hoverPolygon) {
    map?.remove(hoverPolygon)
    hoverPolygon = null
  }
}

function toFeatureCollection(rows, colorFn) {
  return {
    type: 'FeatureCollection',
    features: rows.map((row) => ({
      type: 'Feature',
      properties: { code: row.code, value: row.value, ...(colorFn ? { color: colorFn(row) } : {}) },
      geometry: row.feature.geometry,
    })),
  }
}

function bindScoredEvents(layer) {
  layer.on('mousemove', (e) => {
    if (!map || !e?.feature) return
    const f = e.feature.properties || e.feature
    const row = {
      code: f.code,
      value: Number(f.value) || 0,
      demandWeighted: f.demandWeighted,
      supplyCount: f.supplyCount,
      areaKm2: f.areaKm2,
    }
    popup?.setContent(tooltip(row))
    const lnglat = e.originalEvent?.lnglat || map.getCenter()
    popup?.open(map, lnglat)
    // hover 高亮：描出当前网格轮廓
    const match = featureRows().find((r) => r.code === row.code)
    if (match) {
      if (hoverPolygon) map.remove(hoverPolygon)
      const paths = toPaths(match.feature.geometry)
      if (paths.length) {
        hoverPolygon = new AMap.Polygon({
          path: paths[0],
          strokeColor: '#0f4f3c',
          strokeWeight: 1.8,
          strokeOpacity: 1,
          fillColor: '#ffffff',
          fillOpacity: 0,
          zIndex: 60,
        })
        map.add(hoverPolygon)
      }
    }
  })
  layer.on('mouseout', () => {
    if (hoverPolygon) {
      map.remove(hoverPolygon)
      hoverPolygon = null
    }
    popup?.close()
  })
}

function renderGrid() {
  if (!map || !mapData.value) return
  clearGridLayers()
  const rows = featureRows()
  if (!rows.length) return
  const max = Math.max(0.001, ...rows.map((r) => r.value || 0))
  const scored = rows.filter((r) => r.value > 0)
  const zero = rows.filter((r) => r.value <= 0)
  if (!loca) loca = new Loca.Container({ map })
  if (scored.length) {
    scoredSource = new Loca.GeoJSONSource({
      data: toFeatureCollection(scored, (row) => scoreColor(row.value, max)),
    })
    scoredLayer = new Loca.PolygonLayer({ zIndex: 50 })
    scoredLayer.setSource(scoredSource)
    scoredLayer.setStyle({
      color: (index, feature) => feature?.color || feature?.properties?.color || zeroColor,
      borderColor: '#ffffff',
      borderWidth: 0.35,
      opacity: scoreFillOpacity,
    })
    bindScoredEvents(scoredLayer)
    loca.add(scoredLayer)
  }
  if (zero.length) {
    zeroSource = new Loca.GeoJSONSource({
      data: toFeatureCollection(zero),
    })
    zeroLayer = new Loca.PolygonLayer({ zIndex: 40 })
    zeroLayer.setSource(zeroSource)
    zeroLayer.setStyle({
      color: (index, feature) => zeroColor,
      borderColor: '#ffffff',
      borderWidth: 0.1,
      opacity: zeroFillOpacity,
    })
    loca.add(zeroLayer)
    applyZeroOpacity()
  }
}

/** 渲染当前模式：热力图（默认）或网格 */
function renderLayer() {
  if (!map || !mapData.value) return
  clearGridLayers()
  if (mode.value === 'heatmap') renderHeatmap()
  else renderGrid()
}

function applyZeroOpacity() {
  if (!zeroLayer || !map) return
  const zoom = map.getZoom()
  zeroLayer.setStyle({ opacity: zoom < zeroFadeZoom ? zeroFillOpacity : zeroFillOpacity * 0.2 })
}

// ---------- 热力图渲染 ----------
function renderHeatmap() {
  if (!map || !mapData.value) return
  if (heatmap) {
    heatmap.setMap(null)
    heatmap = null
  }
  const rows = featureRows().filter((r) => r.value > 0)
  const points = gridmapPoints(rows)
  if (!points.length) return
  heatmap = new AMap.HeatMap(map, {
    radius: 38,
    opacity: [0, 0.75],
    gradient: heatGradient,
    zooms: [4, 18],
  })
  heatmap.setDataSet({ data: points, max: 1 })
}

/** 生成热力图数据点：网格几何外包中心 + 评分权重 */
function gridmapPoints(rows) {
  const points = []
  for (const row of rows) {
    const pts = []
    collectPoints(row.feature.geometry, pts)
    if (!pts.length) continue
    let minLng = Infinity,
      minLat = Infinity,
      maxLng = -Infinity,
      maxLat = -Infinity
    for (const p of pts) {
      if (p[0] < minLng) minLng = p[0]
      if (p[0] > maxLng) maxLng = p[0]
      if (p[1] < minLat) minLat = p[1]
      if (p[1] > maxLat) maxLat = p[1]
    }
    const lng = (minLng + maxLng) / 2
    const lat = (minLat + maxLat) / 2
    // 评分映射到权重：0.4（低）~ 1（高），高分在热力中更突出
    const weight = 0.4 + 0.6 * Math.min(1, row.value / 100)
    points.push({ lng, lat, count: weight })
  }
  return points
}

function focusDistrict(code) {
  if (!map || !code) return
  // 聚焦到区县：找到该区县在父级边界集合中的几何
  const polygons = districtBoundaryPolygons.filter((p) => p.getPath?.().length)
  // districtBoundaryPolygons 只含当前父市的区县，若 focusCode 属于当前市则可定位
  if (polygons.length) map.setFitView(polygons, false, [50, 50, 50, 50], 9)
  else if (cityBoundaryPolygons.length) map.setFitView(cityBoundaryPolygons, false, [50, 50, 50, 50], 8)
}

function reset() {
  if (!map) return
  const bounds = gridBounds()
  if (bounds) map.setBounds(bounds, false, [30, 30, 30, 30])
  else map.setZoomAndCenter(7, [112, 27.5])
}

async function fullscreen() {
  if (document.fullscreenElement) await document.exitFullscreen()
  else await root.value?.requestFullscreen().catch(() => {})
}

async function load() {
  const current = ++generation
  abort?.abort()
  abort = new AbortController()
  loading.value = true
  mapData.value = null
  error.value = ''
  clearGridLayers()
  try {
    const data = await planning.layer(
      {
        snapshot_id: planning.snapshot?.snapshotId,
        city: props.parentCode === '430000' ? undefined : props.parentCode,
        adcode: props.scopeCode || undefined,
      },
      abort.signal,
    )
    if (current !== generation) return
    mapData.value = data
    if (map) {
      await drawBoundaries()
      renderLayer()
      if (props.focusCode) focusDistrict(props.focusCode)
      else reset()
    }
  } catch (failure) {
    if (current === generation) error.value = failure.message
  } finally {
    if (current === generation) loading.value = false
  }
}

function onZoomEnd() {
  applyZeroOpacity()
}

async function initializeMap() {
  error.value = ''
  try {
    AMap = await loadAMap()
    Loca = window.Loca
    if (!Loca) throw new Error('LOCA 2.0 加载失败')
    if (disposed) return
    map = new AMap.Map(canvas.value, {
      center: [112.5, 27.6],
      zoom: 7,
      viewMode: '2D',
      dragEnable: true,
      jogEnable: false,
      scrollWheel: true,
      features: ['bg', 'road', 'point'],
      mapStyle: 'amap://styles/normal',
      resizeEnable: true,
      showLabel: true,
    })
    popup = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -10), closeWhenClickMap: true })
    map.addControl(new AMap.Scale())
    map.addControl(new AMap.ToolBar({ position: 'RB' }))
    map.on('zoomend', onZoomEnd)
    if (mapData.value) {
      await drawBoundaries()
      renderLayer()
      if (props.focusCode) focusDistrict(props.focusCode)
      else reset()
    } else {
      reset()
      load()
    }
    resizeObserver = new ResizeObserver(() => map?.resize())
    resizeObserver.observe(canvas.value)
  } catch (cause) {
    console.error('[PlanningMap] 高德地图初始化失败', cause)
    if (!disposed) error.value = '高德地图加载失败，请检查网络与 JS API Key 配置后重试。'
  }
}

onMounted(async () => {
  if (!planning.snapshot && !planning.loading) await planning.load()
  await initializeMap()
  load()
})

watch(
  () => props.parentCode,
  () => {
    load()
  },
)
watch(() => planning.snapshot?.snapshotId, load)
watch(
  () => props.scopeCode,
  () => {
    if (map) load()
  },
)
watch(
  () => props.focusCode,
  () => {
    if (map && props.focusCode) focusDistrict(props.focusCode)
  },
)
watch(mode, () => {
  if (map && mapData.value) {
    clearGridLayers()
    if (mode.value === 'heatmap') renderHeatmap()
    else renderGrid()
  }
})

onBeforeUnmount(() => {
  disposed = true
  ++generation
  abort?.abort()
  resizeObserver?.disconnect()
  clearGridLayers()
  clearBoundaries()
  if (map) {
    map.off('zoomend', onZoomEnd)
    map.destroy()
  }
  loca?.destroy()
  loca = null
  map = null
  popup = null
})
</script>

<template>
  <section ref="root" class="planning-map" :class="{ compact }" aria-label="需求代理评分规划参考地图">
    <header>
      <div>
        <h2>{{ mode === 'heatmap' ? '需求代理评分热力图' : '5km需求代理评分网格' }}</h2>
        <p v-if="!compact">高德底图 · 需求代理评分 · 非建设决策依据 · 样本不代表官方总量</p>
      </div>
      <div class="planning-export-tools">
        <div class="planning-mode-switch" role="group" aria-label="地图显示模式">
          <button
            :class="{ active: mode === 'heatmap' }"
            :aria-pressed="mode === 'heatmap'"
            @click="mode = 'heatmap'"
          >
            热力图
          </button>
          <button
            :class="{ active: mode === 'grid' }"
            :aria-pressed="mode === 'grid'"
            @click="mode = 'grid'"
          >
            网格
          </button>
        </div>
        <button aria-label="规划地图全屏" @click="fullscreen">
          <AppIcon name="expand" :size="17" />
        </button>
      </div>
    </header>
    <div
      ref="canvas"
      class="planning-canvas"
      role="img"
      :aria-label="`需求代理评分${mode === 'heatmap' ? '热力图' : '网格'}地图，颜色表示规划参考评分`"
    />
    <div v-if="error || loading" class="planning-status" :role="error ? 'alert' : 'status'">
      {{ error || '读取需求代理评分图层…' }}<button v-if="error" @click="initializeMap">重试</button>
    </div>
    <div v-else-if="mapData && !featureRows().length" class="planning-status" role="status">
      当前范围没有可显示的评分网格几何。
    </div>
    <div v-if="mode === 'grid'" class="planning-legend">
      <span class="legend-title">需求代理评分</span>
      <span class="legend-zero"><i class="legend-swatch zero" />0 分（弱化）</span>
      <span class="legend-scale"
        ><i class="legend-swatch low" /><i class="legend-swatch mid" /><i class="legend-swatch high" />低
        → 高</span
      >
    </div>
    <div v-else class="planning-legend">
      <span class="legend-title">需求热度</span>
      <span class="legend-scale"
        ><i class="legend-swatch low" /><i class="legend-swatch mid" /><i class="legend-swatch high" />低
        → 高</span
      >
    </div>
    <div class="planning-actions">
      <button aria-label="放大规划地图" @click="map && map.zoomIn()">+</button
      ><button aria-label="缩小规划地图" @click="map && map.zoomOut()">−</button
      ><button aria-label="重置规划地图视角" @click="reset">↺</button>
    </div>
    <footer v-if="!compact">
      需求代理评分 = 需求密度分 × (1 − 周边供给占比)；热力图以评分加权网格生成，供规划参考，不构成建设决策依据。
    </footer>
  </section>
</template>

<style scoped>
.planning-map {
  position: relative;
  background: #f6f9f5;
  border: 1px solid #dbe5df;
  border-radius: 8px;
  height: 100%;
  min-height: 530px;
  overflow: hidden;
}
.planning-map:fullscreen {
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
.planning-export-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}
.planning-mode-switch {
  display: inline-flex;
  background: #fff;
  border: 1px solid #dbe5df;
  border-radius: 5px;
  overflow: hidden;
  pointer-events: auto;
}
.planning-mode-switch button {
  border: 0;
  border-radius: 0;
  padding: 6px 12px;
  font-size: 12px;
  color: #52685c;
  background: transparent;
  cursor: pointer;
}
.planning-mode-switch button.active {
  background: #17634e;
  color: #fff;
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
.planning-canvas {
  position: absolute;
  inset: 112px 12px 58px;
}
.planning-status {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #fff;
  padding: 16px;
  border: 1px solid #dbe5df;
  border-radius: 6px;
  color: #52685c;
  z-index: 4;
}
.planning-status button {
  margin-left: 12px;
  color: #17634e;
}
.planning-legend {
  position: absolute;
  left: 18px;
  bottom: 100px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fffffff2;
  border: 1px solid #dbe5df;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 11px;
  color: #4a6656;
  pointer-events: none;
}
.legend-title {
  font-weight: 600;
  color: #243b35;
}
.legend-zero,
.legend-scale {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.legend-swatch {
  width: 16px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
}
.legend-swatch.zero {
  background: #e0ebe0;
  border: 1px solid #c6d8c6;
}
.legend-swatch.low {
  background: #eef5ef;
}
.legend-swatch.mid {
  background: #5eaa83;
}
.legend-swatch.high {
  background: #17634e;
}
.planning-actions {
  position: absolute;
  right: 18px;
  bottom: 100px;
  display: grid;
  border: 1px solid #dbe5df;
  border-radius: 5px;
  overflow: hidden;
  z-index: 3;
}
.planning-actions button {
  width: 32px;
  height: 32px;
  border: 0;
  background: #fff;
  color: #17634e;
  cursor: pointer;
}
.planning-actions button + button {
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
.compact .planning-canvas {
  inset: 60px 0 15px;
}
.compact .planning-actions {
  bottom: 15px;
}
.compact .planning-legend {
  bottom: 15px;
}
.planning-map :deep(.pm-tip) {
  width: 250px;
  padding: 4px 2px;
  color: #2e4839;
  font-family: inherit;
}
.planning-map :deep(.pm-tip strong) {
  font-size: 14px;
  color: #1e604a;
}
.planning-map :deep(.pm-tip p) {
  margin: 6px 0 8px;
  color: #5c7164;
  font-size: 12px;
  line-height: 1.8;
}
.planning-map :deep(.pm-tip small) {
  display: block;
  border-top: 1px solid #e3eae1;
  padding-top: 7px;
  color: #6b7e70;
  font-size: 10px;
}
</style>