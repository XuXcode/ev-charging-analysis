<script setup>
import { computed, ref, shallowRef, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { MapChart, LineChart } from 'echarts/charts'
import { TooltipComponent, VisualMapComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { http } from '@/api/http'
import { hunan, cityMapConfig } from '@/config/maps'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { roadMetrics, roadCurve } from '@/utils/road-accessibility'
import { download, toCsv } from '@/utils/export'
import { formatNumber } from '@/utils/format'

echarts.use([
  MapChart,
  LineChart,
  TooltipComponent,
  VisualMapComponent,
  GridComponent,
  CanvasRenderer,
])
const props = defineProps({ minutes: { type: Number, required: true } })
const analysis = useAnalysisStore(),
  dashboard = useDashboardStore()
const data = shallowRef(null),
  geometry = shallowRef(hunan)
const error = ref(''),
  loading = ref(false),
  boundaryError = ref('')
const mapElement = ref(null),
  curveElement = ref(null)
let mapChart,
  curveChart,
  observer,
  controller,
  boundaryController,
  geometryVersion = 0,
  disposed = false
const supported = computed(
  () =>
    analysis.classification === 'public_candidate' &&
    !analysis.reviewStatus &&
    !analysis.needsReview &&
    !analysis.batch &&
    !analysis.filterError,
)
const rows = computed(() =>
  (data.value?.regions || []).filter(
    (row) =>
      (!analysis.cityCode || row.cityCode === analysis.cityCode) &&
      (!analysis.districtCode || row.adcode === analysis.districtCode),
  ),
)
const metrics = computed(() => roadMetrics(rows.value, props.minutes))
const ranked = computed(() =>
  [...rows.value].sort(
    (a, b) =>
      (a.complete && Number.isFinite(a.durationSeconds) ? a.durationSeconds : Infinity) -
      (b.complete && Number.isFinite(b.durationSeconds) ? b.durationSeconds : Infinity),
  ),
)
const warnings = computed(() => rows.value.filter((row) => row.completenessWarning).length)
const scopeName = computed(
  () =>
    analysis.districtCatalog.find((r) => r.code === analysis.districtCode)?.name ||
    cityMapConfig[analysis.cityCode]?.name ||
    '湖南省',
)
const finding = computed(() =>
  !metrics.value.resolved
    ? '当前范围没有完整的候选路线观测，暂不形成结论。'
    : `${scopeName.value}已完成 ${metrics.value.resolved}/${metrics.value.total} 个代表点；${metrics.value.reached} 个代表点的候选最短驾车时间在 ${props.minutes} 分钟内。${metrics.value.total - metrics.value.resolved} 个未完成起点未纳入比例分母。`,
)

function exportRoad() {
  if (!supported.value || !data.value) return
  const exported = rows.value.map((row) => ({
    ...row,
    thresholdMinutes: props.minutes,
    jobId: data.value.id,
    algorithmVersion: data.value.algorithmVersion,
    source: '高德路径规划API',
    updatedAt: data.value.updatedAt,
    notice: data.value.notice,
  }))
  const columns = [
    ['adcode', '行政编码'],
    ['name', '区县代表点'],
    ['complete', '观测完整'],
    ['durationSeconds', '候选最短时间(秒)'],
    ['distanceM', '对应道路距离(米)'],
    ['thresholdMinutes', '阈值(分钟)'],
    ['jobId', '道路任务'],
    ['algorithmVersion', '算法版本'],
    ['source', '数据来源'],
    ['updatedAt', '更新时间'],
    ['notice', '方法限制'],
  ].map(([key, label]) => ({ key, label }))
  download(toCsv(columns, exported), '区县代表点道路可达性.csv')
}
async function load() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  error.value = ''
  try {
    const result = await http.get('/analysis/accessibility/latest', { signal: current.signal })
    if (!current.signal.aborted) data.value = result
  } catch (cause) {
    if (!current.signal.aborted) {
      data.value = null
      error.value = cause.message
    }
  } finally {
    if (controller === current) loading.value = false
  }
}
async function loadGeometry() {
  const version = ++geometryVersion
  boundaryController?.abort()
  boundaryError.value = ''
  if (!analysis.cityCode) {
    geometry.value = hunan
    return
  }
  const current = new AbortController()
  boundaryController = current
  geometry.value = null
  try {
    const result = await analysis.boundaries(analysis.cityCode, current.signal)
    if (version === geometryVersion && !disposed) geometry.value = result
  } catch (cause) {
    if (!current.signal.aborted && version === geometryVersion) boundaryError.value = cause.message
  }
}
function select(code) {
  if (cityMapConfig[code]) analysis.$patch({ cityCode: code, districtCode: '' })
  else {
    const row = data.value?.regions.find((r) => r.adcode === code)
    if (row) analysis.$patch({ cityCode: row.cityCode, districtCode: row.adcode })
  }
}
function escape(value) {
  return String(value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  )
}
async function render() {
  await nextTick()
  if (
    disposed ||
    !mapElement.value ||
    !curveElement.value ||
    !supported.value ||
    !geometry.value ||
    !data.value
  )
    return
  if (!mapChart) {
    mapChart = echarts.init(mapElement.value)
    mapChart.on('click', (p) => p.data?.code && select(p.data.code))
    mapChart.on('mouseover', (p) => p.data?.code && dashboard.hoverCity(p.data.code))
    mapChart.on('globalout', () => dashboard.hoverCity(''))
  }
  curveChart ||= echarts.init(curveElement.value)
  const name = `road-${analysis.cityCode || 'province'}`
  echarts.registerMap(name, geometry.value)
  const features = geometry.value.features || []
  const mapRows = features.map((feature) => {
    const code = String(feature.properties.adcode)
    const subset = data.value.regions.filter((r) =>
      analysis.cityCode ? r.adcode === code : r.cityCode === code,
    )
    const statistics = roadMetrics(subset, props.minutes)
    return {
      name: feature.properties.name,
      code,
      value: statistics.percent ?? -1,
      statistics,
      warningCount: subset.filter((r) => r.completenessWarning).length,
      selected: code === analysis.districtCode || code === analysis.cityCode,
    }
  })
  mapChart.setOption(
    {
      animationDurationUpdate: 350,
      tooltip: {
        formatter: (p) => {
          const row = p.data
          if (!row) return escape(p.name)
          return `${escape(p.name)}<br>${props.minutes}分钟代表点可达比例：${formatNumber(row.statistics.percent, 1)}%<br>完成起点：${row.statistics.resolved}/${row.statistics.total}<br>口径：区县内部代表点等权，非面积或人口覆盖${row.warningCount ? '<br>样本完整性警告：' + row.warningCount + '个区县' : ''}`
        },
      },
      visualMap: {
        type: 'piecewise',
        left: 12,
        bottom: 12,
        pieces: [
          { value: -1, label: '未完成', color: '#e4e9e6' },
          { min: 0, max: 25, label: '0–25%', color: '#e1eedf' },
          { min: 25.000001, max: 50, label: '>25–50%', color: '#b1d3b1' },
          { min: 50.000001, max: 75, label: '>50–75%', color: '#61a983' },
          { min: 75.000001, max: 100, label: '>75–100%', color: '#236f53' },
        ],
        textStyle: { color: '#33483d' },
      },
      series: [
        {
          type: 'map',
          map: name,
          roam: true,
          selectedMode: 'single',
          data: mapRows,
          label: { show: true, color: '#163f30', fontSize: 12 },
          itemStyle: { borderColor: '#ffffff', borderWidth: 1.5 },
          emphasis: { itemStyle: { areaColor: '#edce85' } },
          select: { itemStyle: { borderColor: '#c29d35', borderWidth: 3 } },
        },
      ],
    },
    true,
  )
  curveChart.setOption(
    {
      grid: { left: 45, right: 15, bottom: 38, top: 15 },
      tooltip: {
        trigger: 'axis',
        formatter: (p) =>
          `${formatNumber(p[0]?.value?.[0], 1)} 分钟<br>累计代表点：${formatNumber(p[0]?.value?.[1], 1)}%<br>分母为候选路线已完整查询的起点`,
      },
      xAxis: { type: 'value', name: '分钟', nameLocation: 'middle', nameGap: 25 },
      yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        {
          type: 'line',
          step: 'end',
          showSymbol: rows.value.length === 1,
          symbolSize: 6,
          data: roadCurve(rows.value),
          lineStyle: { color: '#236f53', width: 2 },
          areaStyle: { color: '#e1eedf' },
        },
      ],
    },
    true,
  )
  mapChart.resize()
  curveChart.resize()
}
watch([() => analysis.cityCode, () => analysis.snapshot?.metadata.boundaryHash], loadGeometry, {
  immediate: true,
})
watch([data, geometry, rows, () => props.minutes, supported], render)
watch(
  () => dashboard.highlightedCodes,
  (codes) => {
    if (!mapChart) return
    mapChart.dispatchAction({ type: 'downplay' })
    for (const feature of geometry.value?.features || []) {
      if (codes.includes(String(feature.properties.adcode)))
        mapChart.dispatchAction({ type: 'highlight', name: feature.properties.name })
    }
  },
)
onMounted(async () => {
  observer = new ResizeObserver(() => {
    mapChart?.resize()
    curveChart?.resize()
  })
  if (mapElement.value) observer.observe(mapElement.value)
  if (curveElement.value) observer.observe(curveElement.value)
  await load()
  await render()
})
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  boundaryController?.abort()
  observer?.disconnect()
  mapChart?.dispose()
  curveChart?.dispose()
})
</script>
<template>
  <div class="road-analysis">
    <p v-if="!supported" class="road-warning">
      该治理筛选没有对应道路观测。已保存道路任务使用公共候选样本，不回退其他口径。
      <button
        @click="
          analysis.$patch({
            classification: 'public_candidate',
            reviewStatus: '',
            needsReview: false,
            batch: '',
          })
        "
      >
        使用道路观测口径
      </button>
    </p>
    <p v-else-if="error" class="road-warning" role="alert">
      {{ error }} <button @click="load">重新读取</button>
    </p>
    <p v-if="loading" role="status">正在读取保存的道路观测…</p>
    <template v-if="supported && data">
      <div class="road-metrics">
        <section class="panel">
          <span>{{ minutes }}分钟代表点可达比例</span
          ><strong>{{ formatNumber(metrics.percent, 1) }}<small>%</small></strong>
          <p>{{ metrics.reached }}/{{ metrics.resolved }} 个完整起点</p>
        </section>
        <section class="panel">
          <span>平均候选最短时间</span
          ><strong>{{ formatNumber(metrics.meanMinutes, 1) }}<small>分钟</small></strong>
          <p>{{ metrics.measured }} 个有路线的完整起点</p>
        </section>
        <section class="panel">
          <span>对应平均道路距离</span
          ><strong>{{ formatNumber(metrics.meanDistanceKm, 2) }}<small>km</small></strong>
          <p>时间最短候选对应路线</p>
        </section>
      </div>
      <button @click="exportRoad">导出当前范围道路观测 CSV</button>
      <p class="road-finding">{{ finding }}</p>
      <p v-if="warnings || metrics.resolved < metrics.total" class="road-warning">
        {{ warnings }} 个区县存在POI完整性警告；{{ metrics.total - metrics.resolved }}
        个起点尚未完整查询。结果不能解释为实际设施全量或全区县服务覆盖。
      </p>
    </template>
    <div v-show="supported && data" class="road-layout">
      <section class="panel road-map-panel">
        <h2>道路时间专题地图 · {{ minutes }}分钟</h2>
        <p>市州以区县代表点等权汇总；区县每区一个代表点。</p>
        <p v-if="boundaryError" role="alert">{{ boundaryError }}</p>
        <div ref="mapElement" class="road-map" aria-label="道路可达性行政区专题地图" />
      </section>
      <aside class="road-side">
        <section class="panel">
          <h2>候选最短时间累计分布</h2>
          <div ref="curveElement" class="road-curve" aria-label="道路时间累计曲线" />
        </section>
        <section class="panel">
          <h2>区县代表点排行</h2>
          <p>候选最短驾车时间 · 缺失排在最后</p>
          <ol class="road-rank">
            <li v-for="row in ranked" :key="row.adcode">
              <button
                :class="{ selected: analysis.districtCode === row.adcode }"
                @click="select(row.adcode)"
                @mouseenter="dashboard.hoverCity(analysis.cityCode ? row.adcode : row.cityCode)"
                @mouseleave="dashboard.hoverCity('')"
              >
                <span>{{ row.name }}{{ row.completenessWarning ? ' *' : '' }}</span
                ><strong
                  >{{
                    row.complete
                      ? formatNumber(
                          row.durationSeconds === null ? null : row.durationSeconds / 60,
                          1,
                        )
                      : '—'
                  }}
                  分钟</strong
                >
              </button>
            </li>
          </ol>
        </section>
      </aside>
    </div>
    <details v-if="supported && data" class="panel road-provenance">
      <summary>道路计算口径与追溯</summary>
      <p>{{ data.notice }}</p>
      <p>版本：{{ data.algorithmVersion }} · 任务：{{ data.id }} · 状态：{{ data.status }}</p>
      <p>
        来源：{{ data.source }} · 更新时间：{{ data.updatedAt }} · 调用：{{ data.apiCalls }} ·
        缓存：{{ data.cacheHits }}
      </p>
      <p>质量批次：{{ data.qualityBatches.join(' / ') }} · 冻结哈希：{{ data.inputHash }}</p>
      <pre>{{ JSON.stringify(data.parameters, null, 2) }}</pre>
    </details>
  </div>
</template>
<style scoped>
.road-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 16px 0;
}
.road-metrics section,
.road-side section,
.road-map-panel,
.road-provenance {
  padding: 20px;
}
.road-metrics strong {
  display: block;
  font-size: 34px;
  color: var(--primary-dark);
  margin: 8px 0;
}
.road-metrics small {
  font-size: 14px;
  margin-left: 6px;
}
.road-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, 1fr);
  gap: 16px;
}
.road-map {
  height: 620px;
  min-height: 440px;
}
.road-curve {
  height: 240px;
}
.road-side {
  display: grid;
  gap: 16px;
  align-content: start;
}
.road-rank {
  max-height: 310px;
  overflow: auto;
  padding: 0;
  list-style: none;
}
.road-rank button {
  display: flex;
  justify-content: space-between;
  width: 100%;
  padding: 9px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  color: var(--text);
}
.road-rank button:hover,
.road-rank button.selected {
  background: var(--surface-tint);
}
.road-warning {
  padding: 12px;
  color: #74571b;
  background: #fff7e5;
  border-radius: 8px;
}
.road-finding {
  font-size: 15px;
  line-height: 1.7;
}
.road-provenance {
  margin-top: 16px;
  overflow-wrap: anywhere;
}
.road-provenance pre {
  white-space: pre-wrap;
}
@media (max-width: 1100px) {
  .road-layout {
    grid-template-columns: 1fr;
  }
  .road-map {
    height: 500px;
  }
}
</style>
