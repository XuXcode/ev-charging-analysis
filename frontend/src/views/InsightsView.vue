<script setup>
import { computed, ref, shallowRef, onMounted, onBeforeUnmount } from 'vue'
import MonitorLayout from '@/components/layout/MonitorLayout.vue'
import ChartContainer from '@/components/ChartContainer.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { useInsights } from '@/composables/useInsights'
import { http } from '@/api/http'
import { cityMapConfig } from '@/config/maps'
import { classificationLabels, reviewStatusLabels } from '@/config/analysis'
import { snapshotProvenance } from '@/utils/analysis-provenance'
import {
  qualityCharts,
  gridCharts,
  lisaChart,
  roadCharts,
  relationChart,
} from '@/utils/insight-charts'
import { formatNumber } from '@/utils/format'
import '@/styles/insights.css'
const analysis = useAnalysisStore(),
  dashboard = useDashboardStore()
const { snapshot, quality, grid, lisa, road, errors, unavailable, loading, load } = useInsights()
const batches = shallowRef([]),
  batchError = ref('')
const controller = new AbortController()
const governance = computed(() => qualityCharts(quality.value)),
  grids = computed(() => gridCharts(grid.value)),
  roads = computed(() => roadCharts(road.value))
const scopeName = computed(() =>
  analysis.districtCode
    ? snapshot.value?.districts.find((r) => r.code === analysis.districtCode)?.name ||
      `区县 ${analysis.districtCode}`
    : cityMapConfig[analysis.cityCode]?.name || '湖南省',
)
const spatialScope = computed(() =>
  !snapshot.value
    ? null
    : analysis.districtCode
      ? snapshot.value.districts.find((r) => r.code === analysis.districtCode)
      : analysis.cityCode
        ? snapshot.value.cities.find((r) => r.code === analysis.cityCode)
        : snapshot.value.province,
)
const scatterRows = computed(() =>
  (analysis.cityCode
    ? (snapshot.value?.districts || []).filter(
        (r) =>
          r.cityCode === analysis.cityCode &&
          (!analysis.districtCode || r.code === analysis.districtCode),
      )
    : snapshot.value?.cities || []
  ).filter((r) => Number.isFinite(r.density) && Number.isFinite(r.coveragePercent)),
)
const sourceFilters = computed(() => ({
  city: analysis.cityCode,
  district: analysis.districtCode,
  classification: analysis.classification,
  batch: analysis.batch,
  reviewStatus: analysis.reviewStatus,
  needsReview: analysis.needsReview,
}))
const spatialEvidence = computed(() => ({
  ...snapshotProvenance(snapshot.value),
  filters: JSON.stringify({
    ...snapshot.value?.metadata.filters,
    city: analysis.cityCode,
    district: analysis.districtCode,
  }),
}))
const qualityEvidence = computed(() => ({
  source: 'MySQL当前POI治理记录 / 高德POI',
  batch: analysis.batch,
  algorithmName: '按分类与人工核验状态计数',
  filters: JSON.stringify(quality.value?.filters || sourceFilters.value),
  parameters: JSON.stringify({
    observedAt: quality.value?.observedAt,
    version: '当前记录，不是冻结快照',
  }),
  limitations: '分类不证明公共开放或营业状态；与空间快照可能存在时间差。',
}))
const roadEvidence = computed(() => ({
  source: '已保存的高德驾车道路观测',
  algorithmName: '区县几何代表点道路可达性',
  algorithmVersion: road.value?.algorithmVersion,
  computedAt: road.value?.updatedAt,
  qualityBatches: road.value?.qualityBatches?.join(' / '),
  frozenInputHash: road.value?.inputHash,
  filters: JSON.stringify(sourceFilters.value),
  parameters: JSON.stringify({ roadTaskId: road.value?.id, ...road.value?.parameters }),
  limitations: road.value?.notice,
}))
const primary = computed(() => [
  {
    key: 'classification',
    sourceKey: 'quality',
    title: 'POI样本分类构成',
    subtitle: '当前治理记录 · 点击类别联动',
    option: governance.value.pie,
    empty: !governance.value.total,
    loading: loading.value.quality,
    error: errors.value.quality,
    note: governance.value.pieNote,
    provenance: qualityEvidence.value,
    source: 'MySQL当前治理记录 / 高德POI',
  },
  {
    key: 'quality',
    sourceKey: 'quality',
    title: '数据质量与核验状态',
    subtitle: '类别 × 人工核验状态 · 当前治理记录',
    option: governance.value.stacked,
    empty: !governance.value.total,
    loading: loading.value.quality,
    error: errors.value.quality,
    note: governance.value.qualityNote,
    provenance: qualityEvidence.value,
    source: 'MySQL当前治理记录 / 高德POI',
  },
  {
    key: 'density',
    sourceKey: 'grid',
    title: '5km网格密度分布',
    subtitle: '固定网格 · 密度单位：条/km²',
    option: grids.value.density,
    empty: !grid.value.length,
    loading: loading.value.grid,
    error: errors.value.grid,
    note: grids.value.densityNote,
    provenance: spatialEvidence.value,
    source: '冻结空间快照 / 高德POI',
  },
  {
    key: 'pareto',
    sourceKey: 'grid',
    title: '网格样本集中度',
    subtitle: '帕累托视图 · 按样本数降序分组',
    option: grids.value.pareto,
    empty: !grids.value.total,
    loading: loading.value.grid,
    error: errors.value.grid,
    note: grids.value.paretoNote,
    provenance: spatialEvidence.value,
    source: '冻结空间快照 / 高德POI',
  },
])
const spatialCards = computed(() => [
  {
    key: 'lisa',
    sourceKey: 'lisa',
    title: 'LISA空间关联分类',
    subtitle: '既有全省网格统计 · BH-FDR校正',
    option: lisaChart(lisa.value),
    empty: !lisa.value,
    loading: loading.value.lisa,
    error: errors.value.lisa,
    note: lisa.value
      ? `高—高${formatNumber(lisa.value.counts.HH || 0)}个、低—低${formatNumber(lisa.value.counts.LL || 0)}个。范围筛选只统计既有分类，不重新检验局部显著性，也不解释为充电需求。`
      : '当前筛选没有可靠LISA统计，不从密度高低推造分类。',
    provenance: {
      ...spatialEvidence.value,
      algorithmName: '全省固定网格Moran/LISA',
      algorithmVersion: lisa.value?.metadata?.version,
      parameters: JSON.stringify(lisa.value?.metadata || {}),
    },
    source: '冻结LISA空间关联快照',
  },
  {
    key: 'relation',
    sourceKey: 'spatial',
    title: '样本密度与直线覆盖关系',
    subtitle: analysis.cityCode ? '区县尺度 · 点击点联动范围' : '市州尺度 · 点击点联动范围',
    option: relationChart(scatterRows.value),
    empty: !scatterRows.value.length,
    loading: loading.value.spatial,
    error: errors.value.spatial,
    note: `${scatterRows.value.length}个区域，采用同一空间快照的密度与1km直线覆盖率。用于观察差异，不代表因果关系或道路服务水平。`,
    provenance: spatialEvidence.value,
    source: '冻结空间快照 / 高德POI',
  },
])
const roadCards = computed(() => [
  {
    key: 'road-distribution',
    sourceKey: 'road',
    title: '驾车可达时间分布',
    subtitle: '区县代表点 · 候选最短驾车时间',
    option: roads.value.distribution,
    empty: !roads.value.observed,
    loading: loading.value.road,
    error: errors.value.road,
    note: roads.value.distributionNote,
    provenance: roadEvidence.value,
    source: '已保存的高德道路观测',
  },
  {
    key: 'road-curve',
    sourceKey: 'road',
    title: '5/10/15分钟可达比例',
    subtitle: '完整区县代表点等权 · 三个观测阈值',
    option: roads.value.curve,
    empty: !roads.value.denominator,
    loading: loading.value.road,
    error: errors.value.road,
    note: roads.value.curveNote,
    provenance: roadEvidence.value,
    source: '已保存的高德道路观测',
  },
])
const pending = computed(() => Object.values(loading.value).some(Boolean))
function changeCity(event) {
  analysis.$patch({ cityCode: event.target.value, districtCode: '' })
}
function selectClass(point) {
  if (point.insightClassification) analysis.classification = point.insightClassification
}
function selectCity(code) {
  analysis.$patch({ cityCode: code, districtCode: '' })
}
function selectDistrict(code) {
  const row = snapshot.value?.districts.find((r) => r.code === code)
  if (row) analysis.$patch({ cityCode: row.cityCode, districtCode: code })
}
onMounted(async () => {
  try {
    const data = await http.get('/collection/summary', { signal: controller.signal })
    batches.value = [
      { id: data.latestRun?.id, label: '基础采集证据批次' },
      { id: data.latestSupplement?.id, label: '补采证据批次' },
    ].filter((b) => b.id)
  } catch (e) {
    if (!controller.signal.aborted) batchError.value = e.message
  }
})
onBeforeUnmount(() => {
  controller.abort()
  dashboard.hoverCity('')
})
</script>
<template>
  <MonitorLayout scene="insights" panel-title="数据洞察">
    <template #workspace>
      <div class="insights-page">
        <header class="insights-heading">
          <div>
            <span class="insights-eyebrow">DATA INSIGHTS · 真实样本与分析快照</span>
            <h1>
              数据洞察 <small>{{ scopeName }}</small>
            </h1>
          </div>
          <button class="insights-refresh" :disabled="pending" @click="load">
            {{ pending ? '正在读取…' : '刷新数据' }}
          </button>
        </header>
        <form class="insights-filters glass-surface" aria-label="数据洞察筛选" @submit.prevent>
          <label
            >市州<select :value="analysis.cityCode" @change="changeCity">
              <option value="">全省14市州</option>
              <option
                v-for="city in Object.values(cityMapConfig)"
                :key="city.code"
                :value="city.code"
              >
                {{ city.name }}
              </option>
            </select></label
          >
          <label
            >POI分类<select v-model="analysis.classification">
              <option value="">全部类别</option>
              <option v-for="(label, key) in classificationLabels" :key="key" :value="key">
                {{ label }}
              </option>
            </select></label
          >
          <label
            >数据批次<select v-model="analysis.batch">
              <option value="">当前数据集</option>
              <option v-for="batch in batches" :key="batch.id" :value="batch.id">
                {{ batch.label }}
              </option>
              <option
                v-if="analysis.batch && !batches.some((b) => b.id === analysis.batch)"
                :value="analysis.batch"
              >
                指定证据批次
              </option>
            </select></label
          >
          <span class="insights-filter-note">筛选同步全部图表 · 无匹配快照不回退</span
          ><button type="button" @click="analysis.resetFilters()">恢复默认</button>
          <button v-if="analysis.districtCode" type="button" @click="analysis.districtCode = ''">
            清除区县限定
          </button>
          <button
            v-if="analysis.reviewStatus || analysis.needsReview"
            type="button"
            @click="analysis.$patch({ reviewStatus: '', needsReview: false })"
          >
            清除{{ reviewStatusLabels[analysis.reviewStatus] || '待复核线索' }}限定
          </button>
        </form>
        <p v-if="analysis.filterError || batchError" class="insights-notice" role="alert">
          {{ analysis.filterError || `批次目录读取失败：${batchError}` }}
        </p>
        <p v-if="snapshot?.stale" class="insights-notice">
          空间快照已标记过期；展示其冻结结果，不与当前治理计数合并。
        </p>
        <div class="insights-metrics">
          <div>
            <span>当前治理样本</span
            ><strong>{{ quality ? formatNumber(governance.total) : '—' }}<small>条</small></strong>
          </div>
          <div>
            <span>空间快照样本</span
            ><strong
              >{{ spatialScope ? formatNumber(spatialScope.count) : '—' }}<small>条</small></strong
            >
          </div>
          <div>
            <span>有样本网格占比</span
            ><strong
              >{{ grid.length ? formatNumber((grids.positive / grid.length) * 100, 1) : '—'
              }}<small>%</small></strong
            >
          </div>
          <div>
            <span>完整道路代表点</span
            ><strong
              >{{ road ? `${roads.denominator}/${road.regions.length}` : '—'
              }}<small>个</small></strong
            >
          </div>
        </div>
        <div class="insights-section-title">
          <h2>样本结构与空间集中度</h2>
          <span>01—04 · 当前治理记录与冻结网格分别标注</span>
        </div>
        <div class="insights-grid insights-primary">
          <ChartContainer
            v-for="card in primary"
            :key="card.key"
            :title="card.title"
            :subtitle="card.subtitle"
            :option="card.option"
            :empty="card.empty"
            :loading="card.loading"
            :error="card.error"
            :unavailable="unavailable[card.sourceKey]"
            :explanation="card.note"
            :source="card.source"
            :provenance="card.provenance"
            :sample-based="false"
            @point-select="selectClass"
            @retry="load"
            ><p class="insights-reading">
              {{
                card.loading
                  ? '正在读取当前口径数据…'
                  : card.error
                    ? '当前口径缺少可靠数据，未使用其他口径补位。'
                    : card.note
              }}
            </p></ChartContainer
          >
        </div>
        <details class="insights-group">
          <summary>
            <span><b>空间关联与区域关系</b><small>05—06 · 固定网格LISA与同快照区域指标</small></span
            ><span class="insights-group__toggle" aria-hidden="true" />
          </summary>
          <div class="insights-grid">
            <ChartContainer
              v-for="card in spatialCards"
              :key="card.key"
              :title="card.title"
              :subtitle="card.subtitle"
              :option="card.option"
              :empty="card.empty"
              :loading="card.loading"
              :error="card.error"
              :unavailable="unavailable[card.sourceKey]"
              :explanation="card.note"
              :source="card.source"
              :provenance="card.provenance"
              :sample-based="false"
              :highlighted-codes="dashboard.highlightedCodes"
              @city-select="selectCity"
              @district-select="selectDistrict"
              @city-hover="dashboard.hoverCity"
              @city-leave="dashboard.hoverCity('')"
              @retry="load"
              ><p class="insights-reading">
                {{
                  card.loading
                    ? '正在读取当前口径数据…'
                    : card.error
                      ? '当前口径未生成对应快照，不作推算。'
                      : card.note
                }}
              </p></ChartContainer
            >
          </div>
        </details>
        <details class="insights-group">
          <summary>
            <span
              ><b>道路时间与阈值差异</b
              ><small>07—08 · 区县代表点道路观测，不是人口或面积覆盖</small></span
            ><span class="insights-group__toggle" aria-hidden="true" />
          </summary>
          <div class="insights-grid">
            <ChartContainer
              v-for="card in roadCards"
              :key="card.key"
              :title="card.title"
              :subtitle="card.subtitle"
              :option="card.option"
              :empty="card.empty"
              :loading="card.loading"
              :error="card.error"
              :unavailable="unavailable[card.sourceKey]"
              :explanation="card.note"
              :source="card.source"
              :provenance="card.provenance"
              :sample-based="false"
              @retry="load"
              ><p class="insights-reading">
                {{
                  card.loading
                    ? '正在读取当前口径数据…'
                    : card.error
                      ? '道路快照与当前筛选不匹配，不回退公共候选或其他批次结果。'
                      : card.note
                }}
              </p></ChartContainer
            >
          </div>
        </details>
        <details class="insights-method">
          <summary>数据来源、版本与分析方法</summary>
          <dl>
            <div>
              <dt>治理记录读取</dt>
              <dd>{{ quality?.observedAt || '未读取' }} · 当前MySQL治理记录，非冻结空间快照。</dd>
            </div>
            <div>
              <dt>空间快照</dt>
              <dd>
                {{ snapshot?.snapshotId || errors.spatial || '暂无' }} ·
                {{ snapshot?.computedAt }} · {{ snapshot?.metadata.algorithmVersion }}
              </dd>
            </div>
            <div>
              <dt>道路任务</dt>
              <dd>
                {{ road?.id || errors.road || '暂无' }} · {{ road?.updatedAt }} ·
                {{ road?.algorithmVersion }}
              </dd>
            </div>
          </dl>
          <p>
            行政区计数按供应方adcode；筛选网格保留与区域相交的完整固定网格，边缘样本可能跨行政区，不等于所选市州内重新裁切的计数。帕累托分母为网格归属样本总数。LISA保留原全省邻接关系和FDR结果，不在浏览器重新运行统计检验。
          </p>
          <p>
            道路图只读取已保存的代表点观测，不调用高德、不读取自定义地点查询为全省统计。完整无路线起点保留在原比例分母中；未完成起点不作零时间处理。治理记录与空间/道路快照各自保留时间及批次，不拼成同一时点总量。每张图的PNG/CSV携带其独立来源和筛选参数。
          </p>
        </details>
      </div>
    </template>
  </MonitorLayout>
</template>
