<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts/core'
import { bindMapDrag } from '@/utils/map-drag'
import { MapChart } from 'echarts/charts'
import { TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { getAnalysisLayer } from '@/api/analysis'
import { escapeHtml } from '@/utils/format'
import { cityMapConfig } from '@/config/maps'
import AppIcon from '@/components/AppIcon.vue'
import { chartTheme, themeName, mapPalette, token } from '@/utils/chart-theme'
import { exportChartPng, exportChartCsv } from '@/utils/export'
import { snapshotProvenance } from '@/utils/analysis-provenance'
import { cityAnalysisRoute } from '@/utils/analysis-filters'

echarts.use([MapChart, TooltipComponent, VisualMapComponent, CanvasRenderer])
echarts.registerTheme(themeName, chartTheme)
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
const regions = computed(() =>
  props.parentCode === '430000'
    ? analysis.cities
    : analysis.districts.filter((row) => row.cityCode === props.parentCode),
)
const definition = computed(() =>
  layer.value === 'grid' || layer.value === 'hotspots'
    ? { label: '网格POI样本密度', unit: '条/km²', key: 'density' }
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
let chart,
  removeMapDrag,
  observer,
  abort,
  generation = 0,
  zoom = 1,
  center
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
  const d = row.data
  const grid = layer.value === 'grid' || layer.value === 'hotspots'
  return `<strong>${escapeHtml(grid ? '网格 ' + row.code : row.name)}</strong><br/>${escapeHtml(definition.value?.label)}：<b>${number(row.value)} ${escapeHtml(definition.value?.unit)}</b><br/>POI样本：${number(d.count, 'count')} 条${grid ? `<br/>裁切网格面积：${number(d.areaKm2)} km²<br/>${escapeHtml(analysis.snapshot?.metadata.grid.hotspotMethod)}` : `<br/>占全省样本：${number(d.sharePercent, 'sharePercent')}%<br/>待复核线索：${number(d.reviewCount, 'count')} 条<br/>${escapeHtml(d.qualityStatus)}${d.completenessWarning ? '<br/><b>检索触及上限：样本可能不完整</b>' : ''}`}<br/><small>米制近似 · 非官方统计 · ${escapeHtml(analysis.snapshot?.metadata.algorithmVersion)}</small>`
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
  const max = Math.max(0.001, ...rows.map((row) => row.value || 0))
  chart.setOption(
    {
      animation: false,
      tooltip: {
        trigger: 'item',
        confine: true,
        ...chartTheme.tooltip,
        formatter: (p) => tooltip(rows.find((row) => row.code === p.name)),
      },
      visualMap: {
        show: !props.compact,
        min: 0,
        max,
        orient: 'horizontal',
        left: 20,
        bottom: 18,
        calculable: false,
        text: [`${number(max)} ${definition.value?.unit || ''}`, '0'],
        inRange: {
          color: layer.value === 'uncovered' ? ['#f5eddc', '#b18b4b'] : mapPalette,
        },
        textStyle: { color: '#435e50', fontSize: 12 },
      },
      series: [
        {
          type: 'map',
          map: mapName,
          roam: 'scale',
          zoomOnMouseWheel: true,
          moveOnMouseWheel: false,
          zoom,
          center,
          layoutCenter: ['50%', '50%'],
          layoutSize: '98%',
          aspectScale: 0.88,
          data: rows.map((row) => ({
            name: row.code,
            code: row.code,
            value: row.value,
            regionName: cityMapConfig[row.code]?.shortName || row.name,
            label: {
              color: row.value >= max * 0.65 ? token('white') : token('primary-dark'),
              textBorderColor: row.value >= max * 0.65 ? token('map-scale-3') : token('white'),
              textBorderWidth: 1.5,
            },
          })),
          itemStyle: {
            borderColor: '#fff',
            borderWidth: layer.value === 'grid' || layer.value === 'hotspots' ? 0.1 : 1.5,
            areaColor: '#f0f4ef',
          },
          label: {
            show: !props.compact && layer.value === 'regions',
            color: '#244b39',
            fontSize: 13,
            lineHeight: 18,
            formatter: (p) => `${p.data?.regionName}\n${number(p.value)}`,
          },
          emphasis: {
            label: {
              show: !props.compact && layer.value === 'regions',
              color: '#fff',
              fontWeight: 600,
              textBorderColor: 'transparent',
              textBorderWidth: 0,
            },
            itemStyle: {
              areaColor: token('map-hover'),
              borderColor: token('border-strong'),
              borderWidth: 2,
            },
          },
        },
      ],
    },
    true,
  )
  highlight()
}
function highlight() {
  if (!chart) return
  chart.dispatchAction({ type: 'downplay' })
  chart.dispatchAction({ type: 'hideTip' })
  if (props.focusCode) {
    chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: props.focusCode })
    chart.dispatchAction({ type: 'showTip', seriesIndex: 0, name: props.focusCode })
    return
  }
  if (layer.value !== 'regions') return
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
async function load() {
  const current = ++generation
  abort?.abort()
  abort = new AbortController()
  loading.value = true
  mapData.value = null
  chart?.clear()
  error.value = ''
  try {
    const data =
      layer.value === 'regions'
        ? await analysis.boundaries(props.parentCode, abort.signal)
        : await getAnalysisLayer(
            layer.value,
            {
              snapshot_id: analysis.snapshot.snapshotId,
              city: props.parentCode === '430000' ? undefined : props.parentCode,
              adcode: props.scopeCode || undefined,
            },
            abort.signal,
          )
    if (current !== generation) return
    mapData.value = data
    focusRegion()
    render()
  } catch (failure) {
    if (current === generation) error.value = failure.message
  } finally {
    if (current === generation) loading.value = false
  }
}
function focusRegion() {
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
onMounted(() => {
  chart = echarts.init(canvas.value, themeName)
  removeMapDrag = bindMapDrag(chart, canvas.value)
  chart.on('click', (p) => select(p.name))
  chart.on('mouseover', (p) => {
    if (layer.value === 'regions') dashboard.hoverCity(p.name)
  })
  chart.on('globalout', () => dashboard.hoverCity(''))
  chart.on('georoam', () => {
    const current = chart.getOption().series?.[0]
    if (current) {
      zoom = current.zoom
      center = current.center
    }
  })
  observer = new ResizeObserver(() => {
    if (canvas.value?.clientWidth && canvas.value?.clientHeight) {
      chart.resize()
      render()
    }
  })
  observer.observe(canvas.value)
  load()
})
watch(
  () => props.parentCode,
  () => {
    reset()
    load()
  },
)
watch(layer, () => {
  reset()
  load()
})
watch(() => analysis.activeMetric, render)
watch(() => analysis.snapshot?.snapshotId, load)
watch(() => props.scopeCode, load)
watch(() => dashboard.hoveredCityCode, highlight)
watch(() => dashboard.selectedCityCode, highlight)
onBeforeUnmount(() => {
  ++generation
  abort?.abort()
  observer?.disconnect()
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
}
</style>
