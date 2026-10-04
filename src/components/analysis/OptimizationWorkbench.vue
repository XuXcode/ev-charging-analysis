<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { http } from '@/api/http'
import { useAnalysisStore } from '@/stores/analysis'
import PlanningMap from './PlanningMap.vue'
import MapView from '@/components/MapView.vue'
import { formatNumber } from '@/utils/format'
const analysis = useAnalysisStore()
const datasets = ref([]),
  demandId = ref(''),
  candidateId = ref(''),
  n = ref(5),
  algorithm = ref('greedy'),
  metric = ref('straightDistanceM'),
  threshold = ref(1000),
  weights = ref({
    population: 1,
    residential: 0,
    parking: 0,
    commercial: 0,
    office: 0,
    transport: 0,
  })
const variableLabels = {
  population: '人口',
  residential: '居民区',
  parking: '停车场',
  commercial: '商业',
  office: '办公',
  transport: '交通枢纽',
}
const result = ref(null),
  estimate = ref(null),
  error = ref(''),
  loading = ref(false)
let controller,
  disposed = false
const demandOptions = computed(() => datasets.value.filter((r) => r.kind === 'demand'))
const candidateOptions = computed(() => datasets.value.filter((r) => r.kind === 'candidates'))
const supported = computed(
  () =>
    analysis.classification === 'public_candidate' &&
    !analysis.reviewStatus &&
    !analysis.needsReview &&
    !analysis.batch,
)
const canRun = computed(
  () => demandId.value && candidateId.value && analysis.cityCode && supported.value,
)
async function loadDatasets() {
  try {
    const response = await http.get('/analysis/planning/datasets')
    if (!disposed) datasets.value = response.items
  } catch (cause) {
    if (!disposed) error.value = cause.message
  }
}
async function importFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  error.value = ''
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('单个数据文件限10MB，请分批导入。')
    const payload = JSON.parse(await file.text())
    await http.post('/analysis/planning/datasets', payload)
    await loadDatasets()
  } catch (cause) {
    error.value = cause.message
  }
  event.target.value = ''
}
function payload() {
  return {
    demandDatasetId: demandId.value,
    candidateDatasetId: candidateId.value,
    scopeCode: analysis.districtCode || analysis.cityCode,
    weights: weights.value,
    n: n.value,
    algorithm: algorithm.value,
    metric: metric.value,
    threshold: threshold.value,
  }
}
async function execute(estimation = false) {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  error.value = ''
  result.value = null
  estimate.value = null
  try {
    const response = await http.post(
      `/analysis/planning/${estimation ? 'od-estimate' : 'optimization'}`,
      payload(),
      { signal: current.signal, timeout: 150000 },
    )
    if (!current.signal.aborted) {
      if (estimation) estimate.value = response
      else result.value = response
    }
  } catch (cause) {
    if (!current.signal.aborted) error.value = cause.message
  } finally {
    if (!current.signal.aborted) loading.value = false
  }
}
watch(
  () => [
    analysis.cityCode,
    analysis.districtCode,
    analysis.classification,
    analysis.reviewStatus,
    analysis.needsReview,
    analysis.batch,
    demandId.value,
    candidateId.value,
    n.value,
    algorithm.value,
    metric.value,
    threshold.value,
    JSON.stringify(weights.value),
  ],
  () => {
    controller?.abort()
    loading.value = false
    result.value = null
    estimate.value = null
    error.value = ''
  },
)
onMounted(loadDatasets)
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
})
const current = computed(() => result.value?.result)
const focusedCandidate = ref('')
</script>
<template>
  <section class="panel workbench-controls">
    <h2>新增站点方案 · 最大增量需求覆盖</h2>
    <p>
      以真实需求观测和真实设施候选为输入。距离模型与道路时间模型分别计算，现有站已覆盖的需求不重复计入收益。
    </p>
    <div class="planning-controls">
      <label
        >需求数据集<select v-model="demandId">
          <option value="">选择真实数据</option>
          <option v-for="row in demandOptions" :key="row.id" :value="row.id">{{ row.name }}</option>
        </select></label
      >
      <label
        >候选数据集<select v-model="candidateId">
          <option value="">选择真实设施</option>
          <option v-for="row in candidateOptions" :key="row.id" :value="row.id">
            {{ row.name }}
          </option>
        </select></label
      >
      <label>新增预算 N<input v-model.number="n" type="number" min="0" max="100" /></label>
      <label
        >算法<select v-model="algorithm">
          <option value="greedy">Greedy 最大覆盖</option>
          <option value="mclp">MCLP 最大覆盖</option>
        </select></label
      >
      <label
        >服务口径<select v-model="metric">
          <option value="straightDistanceM">直线距离 · 米</option>
          <option value="durationSeconds">道路时间 · 秒</option>
        </select></label
      >
      <label>服务阈值<input v-model.number="threshold" type="number" min="1" max="50000" /></label>
    </div>
    <details>
      <summary>需求权重配置 · 明确的分析参数</summary>
      <div class="planning-controls">
        <label v-for="(label, key) in variableLabels" :key="key"
          >{{ label }}<input v-model.number="weights[key]" type="number" min="0" step="0.1"
        /></label>
      </div>
      <p>
        仅使用有真实数据的变量；非零权重变量缺失或无区分度时停止计算。标准化指数不等于充电需求量。
      </p>
    </details>
    <p v-if="!analysis.cityCode">请通过统一行政区域选择市州或区县，再运行分区方案。</p>
    <p v-if="!supported">当前仅支持公共候选现状口径，其他治理口径待接入，不回退结果。</p>
    <p v-if="!demandOptions.length || !candidateOptions.length" class="planning-warning">
      真实需求或新建候选数据尚未导入；不会生成虚构推荐点或优化收益。
    </p>
    <div class="planning-actions">
      <button :disabled="!canRun || loading" @click="execute()">
        {{ loading ? '正在读取 / 计算…' : '计算方案' }}</button
      ><button :disabled="!canRun || loading" @click="execute(true)">估算候选道路调用量</button
      ><label
        >导入真实证据 JSON<input type="file" accept="application/json,.json" @change="importFile"
      /></label>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="estimate">
      {{ estimate.uniqueOD }}个唯一OD，{{ estimate.estimatedCalls }}次缓存缺失；计入重试最多{{
        estimate.maxAttempts
      }}次。此处实际调用为0，已包含原有站近邻基线。
    </p>
  </section>
  <div class="planning-comparison">
    <section class="panel planning-side">
      <h2>现状 · 原有站点与需求</h2>
      <PlanningMap v-if="current" :existing="current.existingStations" :origins="current.origins" />
      <MapView
        v-else-if="analysis.cityCode"
        :city-code="analysis.cityCode"
        :district-code="analysis.districtCode"
        compact
      />
      <p v-else>选择真实数据集并运行后展示对应现状，不混用1km面积覆盖作为需求覆盖。</p>
      <dl>
        <dt>需求权重覆盖比例</dt>
        <dd>{{ formatNumber(current?.before.coveragePercent, 2) }}{{ current ? '%' : '' }}</dd>
        <dt>未覆盖需求权重</dt>
        <dd>{{ formatNumber(current?.before.uncoveredWeight, 3) }}</dd>
        <dt>平均候选驾车时间</dt>
        <dd>
          {{
            formatNumber(
              current?.averageRoadTimeBefore?.seconds == null
                ? null
                : current.averageRoadTimeBefore.seconds / 60,
              1,
            )
          }}{{ current?.averageRoadTimeBefore?.seconds != null ? ' 分钟' : '' }}
        </dd>
      </dl>
    </section>
    <section class="panel planning-side">
      <h2>方案 · 推荐新增候选</h2>
      <PlanningMap
        v-if="current"
        :existing="current.existingStations"
        :candidates="current.candidates"
        :recommended="current.recommended"
        :focus-id="focusedCandidate"
        :origins="current.origins"
      />
      <p v-else>真实方案待生成。推荐点、覆盖增益和平均道路时间缺失时保持“—”。</p>
      <dl>
        <dt>需求权重覆盖比例</dt>
        <dd>{{ formatNumber(current?.after.coveragePercent, 2) }}{{ current ? '%' : '' }}</dd>
        <dt>未覆盖需求权重</dt>
        <dd>{{ formatNumber(current?.after.uncoveredWeight, 3) }}</dd>
        <dt>平均候选驾车时间</dt>
        <dd>
          {{
            formatNumber(
              current?.averageRoadTimeAfter?.seconds == null
                ? null
                : current.averageRoadTimeAfter.seconds / 60,
              1,
            )
          }}{{ current?.averageRoadTimeAfter?.seconds != null ? ' 分钟' : '' }}
        </dd>
      </dl>
    </section>
  </div>
  <section v-if="current" class="panel planning-side">
    <h2>候选选择与增益</h2>
    <p>
      新增{{ current.recommended.length }}处候选 · 覆盖增益{{
        formatNumber(current.coverageGain, 3)
      }}需求权重 · {{ current.solver.status }}
    </p>
    <ul>
      <li v-for="row in current.recommended" :key="row.id">
        <button @click="focusedCandidate = row.id">{{ row.name }}</button> · {{ row.category }} ·
        {{ row.source }} · {{ row.poiId }}
      </li>
    </ul>
    <p>{{ current.metricNotice }}</p>
    <p v-if="current.averageRoadTimeAfter">
      平均时间仅统计有成功路线的需求点：现状{{ current.averageRoadTimeBefore.validOriginCount }}个，
      方案{{ current.averageRoadTimeAfter.validOriginCount }}个；未成功观测点不以零分钟补入。
    </p>
    <details>
      <summary>需求标准化与候选筛选说明</summary>
      <p>候选点通过边界、重复设施和距原有站约束筛选；尚未验证土地、建设许可和供电条件。</p>
      <pre>{{
        JSON.stringify(
          { normalization: current.demandNormalization, exclusions: current.candidateExclusions },
          null,
          2,
        )
      }}</pre>
    </details>
    <details>
      <summary>版本、参数与数据追溯</summary>
      <p>任务{{ result.id }} · {{ result.createdAt }} · {{ current.algorithmVersion }}</p>
      <p>输入哈希{{ result.inputHash }} · 数据批次{{ current.dataBatches.join(' / ') }}</p>
      <pre>{{
        JSON.stringify({ parameters: result.parameters, solver: current.solver }, null, 2)
      }}</pre>
      <p>{{ current.notice }}</p>
    </details>
  </section>
</template>
<style scoped>
.workbench-controls,
.planning-side {
  padding: 24px;
}
.planning-controls {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 20px 0;
}
.planning-controls label {
  display: grid;
  gap: 8px;
  font-size: 14px;
}
.planning-controls input,
.planning-controls select {
  min-height: 38px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  padding: 6px 10px;
  color: var(--text);
}
.planning-comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0;
}
.planning-side dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
}
.planning-side dd {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--primary-dark);
}
.planning-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.planning-actions button {
  padding: 10px 16px;
  border: 1px solid var(--border);
  background: var(--surface-tint);
  color: var(--primary-dark);
  border-radius: 6px;
  cursor: pointer;
}
.planning-actions button:disabled {
  opacity: 0.5;
  cursor: default;
}
.planning-warning {
  padding: 12px;
  background: #fff7e5;
}
.planning-side pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
@media (max-width: 1100px) {
  .planning-comparison {
    grid-template-columns: 1fr;
  }
  .planning-controls {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
