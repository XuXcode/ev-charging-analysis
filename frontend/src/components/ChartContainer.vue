<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { LegendComponent } from 'echarts/components'
import { chartTheme, themeName, themedOption } from '@/utils/chart-theme'
import { chartRows, exportChartCsv, exportChartPng } from '@/utils/export'
import { useAnalysisStore } from '@/stores/analysis'
import ViewState from '@/components/ViewState.vue'
import { snapshotProvenance } from '@/utils/analysis-provenance'
echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
  DataZoomComponent,
  CanvasRenderer,
  LegendComponent,
])
echarts.registerTheme(themeName, chartTheme)
const props = defineProps({
  title: String,
  subtitle: String,
  option: Object,
  description: String,
  empty: Boolean,
  loading: Boolean,
  error: String,
  explanation: String,
  sampleBased: { type: Boolean, default: true },
  source: String,
  provenance: { type: Object, default: () => ({}) },
  highlightedCodes: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'city-hover',
  'city-leave',
  'city-select',
  'district-select',
  'point-select',
  'retry',
])
const analysis = useAnalysisStore()
const explaining = ref(false),
  exporting = ref(false),
  exportError = ref('')
const container = ref(null)
let chart, observer
function ensureChart() {
  if (
    props.empty ||
    !container.value ||
    chart ||
    !container.value.clientWidth ||
    !container.value.clientHeight
  )
    return
  chart = echarts.init(container.value, themeName)
  chart.on('mouseover', (p) => {
    if (p.data?.cityCode) emit('city-hover', p.data.cityCode)
  })
  chart.on('mouseout', () => emit('city-leave'))
  chart.on('globalout', () => emit('city-leave'))
  chart.on('click', (p) => {
    if (p.data?.gridCellId) {
      emit('point-select', p.data)
      return
    }
    if (p.data?.cityCode) emit('city-select', p.data.cityCode)
    if (p.data?.regionCode && p.data.regionCode !== p.data.cityCode)
      emit('district-select', p.data.regionCode)
  })
}
function update() {
  if (chart && props.option)
    chart.setOption(
      themedOption(
        { aria: { enabled: true, description: props.description || props.title }, ...props.option },
        window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      ),
      true,
    )
  highlight()
}
function highlight() {
  if (!chart) return
  chart.dispatchAction({ type: 'downplay' })
  const data = props.option?.series?.[0]?.data || []
  data.forEach((item, i) => {
    if (props.highlightedCodes.includes(item.cityCode))
      chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: i })
  })
}
onMounted(() => {
  ensureChart()
  update()
  observer = new ResizeObserver(() => {
    if (!container.value?.clientWidth || !container.value?.clientHeight || props.empty) return
    if (!chart) {
      ensureChart()
      update()
    }
    chart?.resize()
  })
  if (container.value) observer.observe(container.value)
})
watch(() => props.option, update, { deep: true })
watch(
  () => props.empty,
  async () => {
    await nextTick()
    ensureChart()
    update()
    chart?.resize()
  },
)
watch(() => props.highlightedCodes, highlight, { deep: true })
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
async function exportResult(format) {
  if (props.empty || props.loading || props.error || exporting.value) return
  exportError.value = ''
  exporting.value = true
  try {
    const provenance = {
      ...(props.sampleBased ? snapshotProvenance(analysis.snapshot) : {}),
      ...props.provenance,
    }
    const source = props.source || (props.sampleBased ? '高德开放平台POI样本' : '可靠统计数据来源')
    if (format === 'png')
      await exportChartPng(chart, props.title, props.subtitle || '', {
        ...provenance,
        source,
      })
    else
      exportChartCsv(props.option, props.title, {
        ...provenance,
        source,
      })
  } catch (failure) {
    exportError.value = failure.message
  } finally {
    exporting.value = false
  }
}
</script>
<template>
  <section class="panel chart-panel">
    <div class="panel-heading">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div class="chart-tools">
        <slot name="actions" />
        <button
          :aria-label="`${title}指标说明`"
          :aria-expanded="explaining"
          @click="explaining = !explaining"
        >
          说明
        </button>
        <button
          :aria-label="`${title}导出PNG`"
          :disabled="empty || loading || !!error || exporting"
          @click="exportResult('png')"
        >
          PNG
        </button>
        <button
          :aria-label="`${title}导出CSV`"
          :disabled="empty || loading || !!error || exporting || !chartRows(option).length"
          @click="exportResult('csv')"
        >
          CSV
        </button>
      </div>
    </div>
    <p v-if="explaining" class="chart-explanation">
      {{
        explanation ||
        description ||
        subtitle ||
        '按当前数据与筛选范围绘制，数值单位见坐标轴及Tooltip。缺失值不按零处理。'
      }}
    </p>
    <div
      v-show="!empty && !loading && !error"
      ref="container"
      class="chart-canvas"
      role="img"
      :aria-label="description || title"
    />
    <ViewState
      v-if="loading || error || empty"
      :kind="loading ? 'loading' : error ? 'error' : 'pending'"
      :description="error || '当前范围尚无可展示的数据；缺失值不等于零。'"
      @retry="emit('retry')"
    />
    <p v-if="exportError" role="alert" class="export-error">{{ exportError }}</p>
    <slot />
  </section>
</template>
<style scoped>
.chart-tools {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}
.chart-tools button {
  min-height: 32px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-small);
  background: var(--surface);
  color: var(--primary-dark);
  font-size: var(--type-caption);
}
.chart-explanation {
  margin: 0 var(--panel-padding) var(--space-3);
  font-size: var(--type-body);
  color: var(--text-secondary);
  line-height: 1.7;
}
.export-error {
  color: var(--danger);
  padding: var(--space-3);
}
</style>
