<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts/core'
import { bindMapDrag } from '@/utils/map-drag'
import { MapChart } from 'echarts/charts'
import { TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useDashboardStore } from '@/stores/dashboard'
import { hunan, cityMapConfig, MAP_COLORS, SAMPLE_CLASSES } from '@/config/maps'
import { escapeHtml, formatNumber } from '@/utils/format'
import AppIcon from '../AppIcon.vue'
echarts.use([MapChart, TooltipComponent, VisualMapComponent, CanvasRenderer])
const props = defineProps({ linked: Boolean, selectionOnly: Boolean, compact: Boolean })
const emit = defineEmits(['city-select'])
const store = useDashboardStore()
const router = useRouter()
const root = ref(null),
  canvas = ref(null),
  hoverCode = ref('')
const summary = computed(() => store.collectionInfo)
const cities = computed(() =>
  Object.values(cityMapConfig).map((city) => ({
    ...city,
    count: summary.value?.cities.find((item) => item.cityCode === city.code)?.storedCount ?? null,
  })),
)
const focusedCity = computed(() => cities.value.find((city) => city.code === hoverCode.value))
const percent = (count) =>
  Number.isFinite(count) && summary.value?.storedCount > 0
    ? `${((count / summary.value.storedCount) * 100).toFixed(2)}%`
    : '—'
const description = computed(() =>
  summary.value
    ? `湖南省${cities.value.length}市州 · ${summary.value.latestRun?.finishedDistricts ?? '—'}区县 · ${formatNumber(summary.value.storedCount)}条有效充电设施POI样本 · 高德开放平台`
    : '湖南省14市州 · 样本数据正在读取 · 高德开放平台',
)
let chart,
  removeMapDrag,
  observer,
  zoom = 1,
  center
function tooltip(city) {
  if (!city) return ''
  return `<div class="province-tooltip"><strong>${escapeHtml(city.name)}</strong><dl><dt>高德可检索POI样本</dt><dd>${formatNumber(city.count)} 条</dd><dt>占全省样本比例</dt><dd>${percent(city.count)}</dd></dl><small>检索样本不代表官方设施总量<br/>点击进入市州站点地图 ↗</small></div>`
}
function option() {
  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: '#fff',
      borderColor: '#d6e3d9',
      textStyle: { color: '#293e33', fontSize: 13 },
      padding: 16,
      formatter: (params) => tooltip(cities.value.find((city) => city.code === params.data?.code)),
    },
    visualMap: {
      show: false,
      type: 'piecewise',
      pieces: SAMPLE_CLASSES,
      seriesIndex: 0,
      outOfRange: { color: MAP_COLORS.empty },
    },
    series: [
      {
        id: 'hunan-samples',
        type: 'map',
        map: 'hunan-province-samples',
        roam: 'scale',
        zoomOnMouseWheel: true,
        moveOnMouseWheel: false,
        zoom,
        center,
        scaleLimit: { min: 0.8, max: 3 },
        layoutCenter: ['50%', '50%'],
        layoutSize: '99%',
        aspectScale: 0.88,
        selectedMode: false,
        data: cities.value.map((city) => ({
          name: city.name,
          code: city.code,
          value: city.count,
          shortName: city.shortName,
          label: { color: city.count >= 1000 ? '#ffffff' : '#244b39' },
        })),
        label: {
          show: !props.compact,
          fontSize: 13,
          lineHeight: 18,
          formatter: (params) =>
            `${params.data?.shortName || params.name}\n${Number.isFinite(params.value) ? params.value.toLocaleString('zh-CN') : '—'}`,
        },
        itemStyle: {
          areaColor: MAP_COLORS.empty,
          borderColor: '#ffffff',
          borderWidth: 2,
          shadowColor: '#2b61441a',
          shadowBlur: 15,
          shadowOffsetY: 4,
        },
        emphasis: {
          label: {
            show: !props.compact,
            color: '#ffffff',
            fontWeight: 600,
            textBorderWidth: 0,
          },
          itemStyle: { areaColor: MAP_COLORS.emphasis, borderColor: '#b1d2bd', borderWidth: 2.5 },
        },
      },
    ],
  }
}
function render() {
  if (chart && canvas.value?.clientWidth > 0 && canvas.value?.clientHeight > 0) {
    chart.setOption(option(), true)
    highlight()
  }
}
function highlight() {
  if (!chart) return
  chart.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  for (const code of store.highlightedCodes)
    if (cityMapConfig[code])
      chart.dispatchAction({ type: 'highlight', seriesIndex: 0, name: cityMapConfig[code].name })
  const code = store.hoveredCityCode
  hoverCode.value = code || ''
  const dataIndex = cities.value.findIndex((city) => city.code === code)
  if (dataIndex >= 0) chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex })
  else chart.dispatchAction({ type: 'hideTip' })
}
function reset() {
  zoom = 1
  center = undefined
  render()
}
function changeZoom(step) {
  zoom = Math.max(0.8, Math.min(3, zoom + step))
  render()
}
async function fullscreen() {
  if (document.fullscreenElement) await document.exitFullscreen()
  else await root.value.requestFullscreen().catch(() => {})
}
function openCity(code) {
  if (!cityMapConfig[code]) return
  if (props.selectionOnly) {
    store.selectCity(code)
    store.hoverCity(code)
    emit('city-select', code)
    return
  }
  store.hoverCity()
  router.push(`/city/${code}`)
}
onMounted(() => {
  echarts.registerMap('hunan-province-samples', hunan)
  chart = echarts.init(canvas.value)
  removeMapDrag = bindMapDrag(chart, canvas.value)
  render()
  chart.on('click', (params) => openCity(params.data?.code))
  chart.on('mouseover', (params) => {
    hoverCode.value = params.data?.code || ''
    store.hoverCity(hoverCode.value)
  })
  chart.on('globalout', () => {
    hoverCode.value = ''
    store.hoverCity()
  })
  chart.on('georoam', () => {
    const current = chart.getOption().series[0]
    zoom = current.zoom
    center = current.center
  })
  observer = new ResizeObserver(() => {
    const width = canvas.value?.clientWidth
    const height = canvas.value?.clientHeight
    // Fullscreen and responsive layout can briefly report a zero-sized container.
    // A zero-sized Geo transform has no inverse; wait for the next valid layout.
    if (width > 0 && height > 0) chart?.resize({ width, height })
  })
  observer.observe(canvas.value)
  if (!summary.value) store.loadCollectionInfo()
})
watch(() => store.collectionInfo, render)
watch(() => store.highlightedCodes, highlight, { deep: true })
onBeforeUnmount(() => {
  observer?.disconnect()
  removeMapDrag?.()
  chart?.dispose()
  chart = null
  store.hoverCity()
})
</script>
<template>
  <section ref="root" class="province-map" aria-label="湖南省充电设施POI样本专题地图">
    <header class="province-map-header">
      <div>
        <span class="map-eyebrow">省级空间格局</span>
        <h2>湖南省充电设施POI样本分布</h2>
        <p>按市州样本数量分级设色 · 点击进入市州站点地图</p>
      </div>
      <button class="icon-button" aria-label="省级地图全屏" @click="fullscreen">
        <AppIcon name="expand" :size="17" />
      </button>
    </header>
    <div
      ref="canvas"
      class="province-map-canvas"
      role="img"
      aria-label="湖南省14市州真实行政边界，颜色表示高德可检索POI样本数；可使用右侧市州列表进入详情"
    />
    <aside class="province-map-legend">
      <strong>POI样本数 <small>条</small></strong>
      <span v-for="piece in SAMPLE_CLASSES" :key="piece.label"
        ><i :style="{ background: piece.color }" />{{ piece.label }}</span
      >
      <small>固定数量区间<br />无统计密度含义</small>
    </aside>
    <div class="province-focus" aria-live="polite">
      <template v-if="focusedCity"
        ><span>{{ focusedCity.name }}</span
        ><strong>{{ formatNumber(focusedCity.count) }} <small>条</small></strong>
        <p>占全省样本 {{ percent(focusedCity.count) }}</p></template
      >
      <template v-else
        ><span>高德可检索POI样本</span
        ><strong>{{ summary ? formatNumber(summary.storedCount) : '—' }} <small>条</small></strong>
        <p>检索样本，不代表官方设施总量</p></template
      >
    </div>
    <div class="province-map-actions">
      <button aria-label="放大省级地图" @click="changeZoom(0.2)">+</button
      ><button aria-label="缩小省级地图" @click="changeZoom(-0.2)">−</button
      ><button aria-label="重置省级地图" @click="reset">
        <AppIcon name="target" :size="16" />
      </button>
    </div>
    <footer class="province-map-footer">
      <span>{{ description }}</span
      ><small v-if="store.collectionError" role="alert"
        >{{ store.collectionError }}
        <button @click="store.loadCollectionInfo()">重试</button></small
      >
    </footer>
  </section>
</template>
<style scoped>
.province-map {
  position: relative;
  height: 100%;
  min-height: 530px;
  background: #f5f8f4;
  overflow: hidden;
}
.province-map:fullscreen {
  height: 100vh;
}
.province-map-header {
  position: absolute;
  top: 20px;
  left: 24px;
  right: 20px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  z-index: 2;
  pointer-events: none;
}
.province-map-header button {
  pointer-events: auto;
}
.map-eyebrow {
  color: var(--primary);
  font-size: 12px;
  letter-spacing: 1px;
}
.province-map-header h2 {
  font-size: 19px;
  font-weight: 600;
  margin: 5px 0;
}
.province-map-header p {
  font-size: 12px;
  color: var(--muted);
}
.province-map-canvas {
  position: absolute;
  inset: 80px 12px 46px;
}
.province-map-legend {
  position: absolute;
  left: 24px;
  bottom: 76px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  pointer-events: none;
  font-size: 12px;
}
.province-map-legend strong {
  margin-bottom: 5px;
  font-size: 13px;
  font-weight: 600;
}
.province-map-legend span {
  display: flex;
  align-items: center;
  gap: 8px;
}
.province-map-legend i {
  width: 25px;
  height: 12px;
  border: 1px solid #95b49f55;
  border-radius: 2px;
}
.province-map-legend small {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}
.province-focus {
  position: absolute;
  right: 24px;
  top: 112px;
  font-size: 12px;
  color: var(--muted);
  text-align: right;
  pointer-events: none;
}
.province-focus strong {
  display: block;
  margin: 5px 0;
  color: var(--primary-dark);
  font-size: 26px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.province-focus strong small {
  font-size: 12px;
  font-weight: 400;
}
.province-map-actions {
  position: absolute;
  right: 20px;
  bottom: 70px;
  display: flex;
  flex-direction: column;
  background: white;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.province-map-actions button {
  width: 34px;
  height: 34px;
  border: 0;
  background: white;
  color: var(--primary-dark);
  display: grid;
  place-items: center;
}
.province-map-actions button + button {
  border-top: 1px solid var(--border);
}
.province-map-footer {
  position: absolute;
  bottom: 0;
  width: 100%;
  background: #ffffffc9;
  border-top: 1px solid var(--border);
  padding: 11px 18px;
  font-size: 12px;
  color: #4d6856;
  line-height: 1.7;
}
@media (max-width: 1500px) {
  .province-focus {
    display: none;
  }
}
@media (max-width: 1300px) {
  .province-focus {
    top: 108px;
    right: 16px;
    max-width: 125px;
  }
  .province-focus strong {
    font-size: 22px;
  }
  .province-map-legend {
    left: 18px;
    bottom: 82px;
    gap: 7px;
  }
  .province-map-header h2 {
    font-size: 16px;
  }
  .province-map-canvas {
    inset: 85px 0 62px;
  }
}
@media (max-width: 760px) {
  .province-map {
    min-height: 620px;
  }
  .province-focus {
    display: none;
  }
  .province-map-legend {
    bottom: 76px;
  }
  .province-map-canvas {
    inset: 86px 0 150px;
  }
  .province-map-footer {
    font-size: 11px;
  }
}
</style>
