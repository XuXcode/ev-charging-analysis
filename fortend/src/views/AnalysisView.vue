<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { topics } from '@/mock/topics'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import { cityMapConfig } from '@/config/maps'
import MapView from '@/components/MapView.vue'
import ChartContainer from '@/components/ChartContainer.vue'
import AnalysisSlot from '@/components/analysis/AnalysisSlot.vue'
import AnalysisProvenance from '@/components/analysis/AnalysisProvenance.vue'
import CountyComparison from '@/components/analysis/CountyComparison.vue'
import RoadAccessibility from '@/components/analysis/RoadAccessibility.vue'
import OptimizationWorkbench from '@/components/analysis/OptimizationWorkbench.vue'
import LowAccessibility from '@/components/analysis/LowAccessibility.vue'
import { snapshotProvenance } from '@/utils/analysis-provenance'
import { formatNumber } from '@/utils/format'
import { download, toCsv } from '@/utils/export'
import { cityAnalysisRoute, analysisFilterQuery } from '@/utils/analysis-filters'
import {
  comparisonMetrics,
  comparisonOption,
  coverageDistribution,
  densityCoverageOption,
} from '@/utils/analysis-charts'
const route = useRoute()
const router = useRouter()
const store = useDashboardStore()
const analysis = useAnalysisStore()
const slug = computed(() => route.params.topic)
const topic = computed(() => topics.find((t) => t.slug === slug.value))
const mode = computed({
  get: () =>
    ['5', '10', '15'].includes(route.query.travel_time) ? `${route.query.travel_time}分钟` : '1km',
  set: (value) => {
    const query = { ...route.query }
    if (value === '1km') delete query.travel_time
    else query.travel_time = String(parseInt(value))
    router.replace({ path: route.path, query })
  },
})
const selected = computed({
  get: () => analysis.cityCode,
  set: (value) => {
    analysis.cityCode = value
  },
})
const sourceTime = computed(() =>
  store.collectionInfo?.updatedAt
    ? new Date(store.collectionInfo.updatedAt).toLocaleString('zh-CN')
    : '等待数据服务',
)
const metricKey = computed({
  get: () => analysis.activeMetric,
  set: (value) => {
    analysis.activeMetric = value
  },
})
const metric = computed(() => comparisonMetrics.find((item) => item.key === metricKey.value))
const cityRows = computed(() => (analysis.cities.length ? analysis.cities : []))
const districts = computed(() =>
  analysis.districts.filter(
    (r) =>
      (!selected.value || r.cityCode === selected.value) &&
      (!analysis.districtCode || r.code === analysis.districtCode),
  ),
)
const scopeMetrics = computed(() =>
  analysis.districtCode
    ? analysis.districts.find((r) => r.code === analysis.districtCode)
    : selected.value
      ? analysis.cities.find((r) => r.code === selected.value)
      : analysis.snapshot?.province,
)
const spatialRows = computed(() =>
  selected.value ? [...districts.value].sort((a, b) => b.count - a.count) : cityRows.value,
)
const coverageRank = computed(() =>
  [...districts.value].sort((a, b) => a.coveragePercent - b.coveragePercent),
)
const issueRows = computed(() =>
  [...analysis.districts]
    .filter((row) => !selected.value || row.cityCode === selected.value)
    .sort((a, b) => a.coveragePercent - b.coveragePercent),
)
const locatedDistrict = computed({
  get: () => analysis.districtCode,
  set: (value) => {
    analysis.districtCode = value
  },
})
const located = computed(() => districts.value.find((r) => r.code === locatedDistrict.value))
const chart = computed(() => comparisonOption(cityRows.value, metric.value, selected.value))
const curve = computed(() => coverageDistribution(districts.value))
const scatter = computed(() => densityCoverageOption(analysis.cities))
function exportIssues() {
  if (!analysis.snapshot || !issueRows.value.length) return
  const rows = issueRows.value.map((row) => ({
    ...row,
    ...snapshotProvenance(analysis.snapshot),
    risk: '未评级',
    warning: row.completenessWarning ? '检索触及上限，样本可能不完整' : '',
  }))
  const columns = [
    ['code', '行政编码'],
    ['name', '区县'],
    ['count', 'POI样本数量(条)'],
    ['coveragePercent', '1km直线样本覆盖率(%)'],
    ['uncoveredAreaKm2', '样本未覆盖面积(km²)'],
    ['reviewCount', '待复核线索(条)'],
    ['risk', '风险等级'],
    ['warning', '完整性提示'],
    ['source', '来源'],
    ['snapshotId', '分析快照'],
    ['batch', '数据批次'],
    ['qualityBatches', '当前样本证据批次'],
    ['datasetBatches', '完整数据集证据批次'],
    ['algorithmName', '算法名称'],
    ['algorithmVersion', '算法版本'],
    ['collectedAt', '数据集采集更新时间'],
    ['computedAt', '计算时间'],
    ['filters', '快照样本口径'],
    ['parameters', '算法参数与依赖版本'],
    ['frozenInputHash', '冻结输入哈希'],
    ['limitations', '已知限制'],
  ].map(([key, label]) => ({ key, label }))
  download(toCsv(columns, rows), '区县样本未覆盖清单.csv')
}
function locate(row) {
  focus(row.cityCode)
  locatedDistrict.value = row.code
}
onMounted(() => {
  analysis.load()
  store.loadCollectionInfo()
})
function focus(code) {
  selected.value = code
  locatedDistrict.value = ''
  store.selectCity(code)
  store.hoverCity(code)
}
watch(slug, () => {
  store.hoverCity('')
})
</script>
<template>
  <div class="analysis-page" v-if="topic" :class="`topic-${slug}`">
    <header class="page-intro">
      <div>
        <h1>{{ topic.title }}</h1>
        <p>{{ topic.description }}</p>
      </div>
      <router-link
        :to="{
          path: '/',
          query: analysisFilterQuery({ ...analysis, cityCode: '', districtCode: '' }),
        }"
        class="back-link"
        >返回全省总览</router-link
      >
    </header>
    <div class="analysis-context">
      <span
        >{{ selected ? cityMapConfig[selected]?.name : '湖南省 · 14市州' }} · 高德POI样本 · 更新
        {{ sourceTime }}</span
      ><router-link
        v-if="selected"
        :to="cityAnalysisRoute(analysis, selected, analysis.districtCode)"
        class="back-link"
        >查看市州站点 ↗</router-link
      >
    </div>
    <p v-if="analysis.loading" class="analysis-warning" role="status">
      正在读取当前筛选的分析快照…
    </p>
    <p v-else-if="analysis.error" class="analysis-warning" role="alert">
      分析快照暂不可用：{{ analysis.error }}
      <button @click="analysis.load(true)">重试分析快照</button>
    </p>
    <p v-if="store.collectionError" class="analysis-warning" role="alert">
      {{ store.collectionError }} <button @click="store.loadCollectionInfo()">重试</button>
    </p>
    <div v-if="slug === 'spatial'" class="analysis-split spatial">
      <section class="analysis-main-map">
        <MapView
          linked
          selection-only
          analysis-layers
          :parent-code="selected || '430000'"
          :focus-code="locatedDistrict"
          :scope-code="locatedDistrict"
          @city-select="focus"
          @district-select="(code) => (locatedDistrict = code)"
        />
      </section>
      <aside class="analysis-stack">
        <section class="panel analysis-panel">
          <h2>{{ selected ? '区县样本分布' : '市州分布与集聚' }}</h2>
          <p>按行政区与网格观察样本空间差异。</p>
          <ul class="analysis-rank">
            <li v-for="row in spatialRows" :key="row.code">
              <button
                @mouseenter="store.hoverCity(row.code)"
                @mouseleave="store.hoverCity('')"
                @focus="store.hoverCity(row.code)"
                @blur="store.hoverCity('')"
                @click="selected ? locate(row) : focus(row.code)"
              >
                <span>{{ row.name }}{{ row.completenessWarning ? ' *' : '' }}</span
                ><strong>{{ formatNumber(row.count) }} 条</strong>
              </button>
            </li>
          </ul>
        </section>
        <section v-if="analysis.snapshot" class="panel analysis-panel">
          <h2>全省快照 · 网格与聚集口径</h2>
          <p>
            {{ analysis.snapshot.metadata.grid.cellCount.toLocaleString() }}个5km裁切网格，纳入{{
              analysis.snapshot.metadata.grid.assignedCount.toLocaleString()
            }}条样本；{{
              analysis.snapshot.metadata.grid.outsideBoundaryCount
            }}条省级几何外样本单列。
          </p>
          <p>
            {{ analysis.snapshot.metadata.grid.hotspotMethod }}；阈值{{
              analysis.snapshot.metadata.grid.hotspotThreshold
            }}条/km²。
          </p>
          <p class="analysis-warning">
            部分区县检索触及上限，样本可能不完整。{{ analysis.snapshot.metadata.coordinateNotice }}
          </p>
        </section>
        <AnalysisSlot
          v-else
          title="网格密度 / 热点聚集"
          description="等待真实边界与计算快照；热点不能由站点数量直接认定。"
        />
      </aside>
    </div>
    <template v-else-if="slug === 'accessibility'">
      <section class="panel analysis-panel">
        <h2>样本覆盖与出行可达性</h2>
        <div class="analysis-tabs" role="group" aria-label="覆盖分析模式">
          <button
            v-for="item in ['1km', '5分钟', '10分钟', '15分钟']"
            :key="item"
            :class="{ active: mode === item }"
            @click="mode = item"
          >
            {{ item }}
          </button>
        </div>
        <p>
          {{
            mode === '1km'
              ? '1km直线样本覆盖：几何范围，不代表真实道路可达。'
              : '真实驾车时间观测：区县内部代表点到附近公共候选站点，非面积或人口覆盖。'
          }}
        </p>
      </section>
      <div v-if="mode === '1km' && scopeMetrics" class="analysis-metrics">
        <section class="panel analysis-kpi">
          <span>1km直线样本覆盖率</span
          ><strong>{{ formatNumber(scopeMetrics.coveragePercent, 2) }}<small>%</small></strong>
          <p>缓冲区合并后与行政边界相交</p>
        </section>
        <section class="panel analysis-kpi">
          <span>样本未覆盖面积</span
          ><strong>{{ formatNumber(scopeMetrics.uncoveredAreaKm2, 1) }}<small>km²</small></strong>
          <p>行政区面积减去样本覆盖面积</p>
        </section>
        <section class="panel analysis-kpi">
          <span>纳入区县</span><strong>{{ districts.length }}<small>个</small></strong>
          <p>区县等权分布 · 非道路可达性</p>
        </section>
      </div>
      <RoadAccessibility v-if="mode !== '1km'" :minutes="parseInt(mode)" />
      <div v-if="mode === '1km'" class="analysis-split">
        <section class="panel analysis-panel">
          <h2>
            {{ mode === '1km' && located ? `${located.name} · 站点与覆盖` : `${mode}分析地图` }}
          </h2>
          <MapView
            v-if="mode === '1km' && analysis.snapshot"
            :key="'coverage-' + selected"
            :parent-code="selected || '430000'"
            initial-layer="coverage"
            :focus-code="locatedDistrict"
            :scope-code="locatedDistrict"
            linked
            selection-only
            @city-select="focus"
            @district-select="(code) => (locatedDistrict = code)"
          />
          <AnalysisSlot
            v-else
            :title="mode === '1km' ? '覆盖快照待接入' : '道路等时圈待接入'"
            description="5/10/15分钟出行可达性需要道路网络与出行模型，本阶段未计算。"
          />
        </section>
        <aside v-if="mode === '1km' && analysis.snapshot" class="analysis-stack">
          <ChartContainer
            title="区县覆盖累计分布"
            :loading="analysis.loading"
            subtitle="横轴为覆盖率，纵轴为累计区县比例 · 区县等权"
            :option="curve"
            :empty="!districts.length"
            :highlighted-codes="store.highlightedCodes"
            @city-hover="store.hoverCity"
            @city-leave="store.hoverCity('')"
            @city-select="focus"
            @district-select="(code) => (locatedDistrict = code)"
          />
          <section class="panel analysis-panel">
            <h2>区县样本覆盖排行</h2>
            <p>覆盖率从低到高 · 展示前12个区县</p>
            <ol class="analysis-rank">
              <li v-for="row in coverageRank.slice(0, 12)" :key="row.code">
                <button
                  @click="locate(row)"
                  @mouseenter="store.hoverCity(row.cityCode)"
                  @mouseleave="store.hoverCity('')"
                >
                  <span>{{ row.name }}{{ row.completenessWarning ? ' *' : '' }}</span
                  ><strong>{{ formatNumber(row.coveragePercent, 2) }}%</strong>
                </button>
              </li>
            </ol>
          </section>
        </aside>
        <aside v-else class="analysis-stack">
          <AnalysisSlot
            title="可达性分布 / 累计曲线"
            description="等待真实道路出行计算结果。"
          /><AnalysisSlot title="区县可达性排行" description="不能用直线覆盖率代替分钟可达性。" />
        </aside>
      </div>
    </template>
    <div v-else-if="slug === 'supply-demand'" class="analysis-split">
      <section class="panel analysis-panel">
        <h2>供给 × 需求关系</h2>
        <p>供需四象限 · 统计口径待确定</p>
        <div class="analysis-quadrants" aria-label="供需四象限结构预留，无分析点位">
          <span>高需求 / 低供给</span><span>高需求 / 高供给</span><span>低需求 / 低供给</span
          ><span>低需求 / 高供给</span>
          <div>供需结果待接入<small>未计算供需指数或模拟点位</small></div>
        </div>
        <p>横轴：供给能力 · 纵轴：充电需求。POI样本数量不能代替充电容量或需求。</p>
      </section>
      <aside class="analysis-stack">
        <AnalysisSlot
          title="供给与需求口径"
          description="可靠的桩数、功率、车辆保有量与需求数据尚未接入。"
        />
        <section class="panel analysis-panel">
          <h2>辅助区域定位</h2>
          <p>用于定位，不表示供需分区。</p>
          <div class="analysis-small-map">
            <MapView compact linked selection-only @city-select="focus" />
          </div>
        </section>
      </aside>
    </div>
    <template v-else-if="slug === 'differences'">
      <div class="analysis-split">
        <ChartContainer
          class="analysis-comparison-chart"
          :loading="analysis.loading"
          :title="`14市州${metric.label}差异`"
          subtitle="同一真实快照 · 非官方设施统计"
          :option="chart"
          :empty="!cityRows.length"
          :highlighted-codes="store.highlightedCodes"
          @city-hover="store.hoverCity"
          @city-leave="store.hoverCity('')"
          @city-select="focus"
          ><template #actions
            ><select v-model="metricKey" aria-label="市州对比指标">
              <option
                v-for="item in comparisonMetrics"
                :key="item.key"
                :value="item.key"
                :disabled="item.key !== 'count' && !analysis.snapshot"
              >
                {{ item.label }}
              </option>
            </select></template
          ></ChartContainer
        >
        <aside class="analysis-stack">
          <section class="panel analysis-panel">
            <h2>区域选择与定位</h2>
            <p>悬停柱条高亮区域，点击选择市州。区域选择与排名、辅助地图联动。</p>
            <div class="analysis-small-map">
              <MapView compact linked selection-only @city-select="focus" />
            </div>
          </section>
          <ChartContainer
            v-if="analysis.snapshot"
            :loading="analysis.loading"
            title="样本密度 × 直线覆盖率"
            subtitle="14市州 · 密度与覆盖关系，不代表因果关系"
            :option="scatter"
            :highlighted-codes="store.highlightedCodes"
            @city-hover="store.hoverCity"
            @city-leave="store.hoverCity('')"
            @city-select="focus"
          />
          <AnalysisSlot v-else title="样本密度 × 覆盖散点" description="等待真实分析快照。" />
        </aside>
      </div>
      <details class="analysis-extension">
        <summary>区县对比与分布异常值</summary>
        <CountyComparison
          :rows="analysis.districts.filter((row) => !selected || row.cityCode === selected)"
          v-model:metric="metricKey"
          :loading="analysis.loading"
          :scope-name="selected ? cityMapConfig[selected]?.name : '全省122区县'"
          @select="locate"
          @hover="store.hoverCity"
        />
      </details>
      <details class="analysis-extension">
        <summary>其他比较维度 · 数据待接入</summary>
        <div class="analysis-two-up">
          <AnalysisSlot
            title="结构与时间差异"
            description="可靠的设施结构、年份和历史统计待接入。"
            compact
          />
        </div>
      </details>
    </template>
    <LowAccessibility v-else-if="slug === 'underserved'" />
    <OptimizationWorkbench v-else-if="slug === 'optimization'" />
    <footer class="analysis-method">
      <strong>数据与方法</strong
      ><span
        >高德可检索POI样本，不代表官方设施总量。*
        表示检索触及上限，样本可能不完整。1km为直线几何覆盖，非道路可达性。</span
      >
    </footer>
    <AnalysisProvenance
      v-if="
        !['optimization', 'underserved'].includes(slug) &&
        (slug !== 'accessibility' || mode === '1km')
      "
    />
  </div>
</template>
<style scoped>
.issue-export {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
  background: var(--surface);
  color: var(--primary-dark);
  min-height: 36px;
  margin: 8px 0;
  cursor: pointer;
}
.analysis-extension {
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
.analysis-extension summary {
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--space-2) 0;
}
.topic-differences .analysis-split {
  grid-template-columns: minmax(0, 2.2fr) minmax(310px, 1fr);
}
.topic-supply-demand .analysis-split {
  grid-template-columns: minmax(0, 2fr) minmax(300px, 0.9fr);
}
.topic-underserved .analysis-split {
  grid-template-columns: minmax(0, 1.65fr) minmax(330px, 1fr);
}
.topic-underserved .analysis-split > .analysis-panel {
  max-height: 680px;
  overflow: auto;
}
.topic-underserved .analysis-issue-table thead {
  position: sticky;
  top: -22px;
  z-index: 1;
}
.analysis-rank button[aria-pressed='true'] {
  background: var(--primary-soft);
  color: var(--primary-dark);
}
@media (min-width: 1700px) {
  .topic-spatial .analysis-main-map {
    min-height: 620px;
  }
  .topic-optimization .analysis-plan-map {
    height: 470px;
  }
  .topic-optimization .analysis-plan > :last-child :deep(.analysis-slot) {
    min-height: 470px;
  }
}
@media (max-width: 1450px) and (min-width: 901px) {
  .analysis-main-map {
    min-height: 510px !important;
  }
  .analysis-comparison-chart {
    min-height: 550px !important;
    height: 550px !important;
  }
  .analysis-comparison-chart :deep(.chart-canvas) {
    min-height: 430px !important;
    height: 430px !important;
  }
  .analysis-quadrants {
    min-height: 390px !important;
  }
  .topic-optimization .analysis-plan-map {
    height: 400px;
  }
  .topic-optimization .analysis-plan > :last-child :deep(.analysis-slot) {
    min-height: 400px;
  }
}
@media (max-width: 900px) {
  .topic-differences .analysis-split,
  .topic-supply-demand .analysis-split,
  .topic-underserved .analysis-split {
    grid-template-columns: 1fr;
  }
}
.analysis-kpi {
  padding: 22px;
}
.analysis-kpi > span {
  color: var(--text-secondary);
  font-size: 14px;
}
.analysis-kpi strong {
  display: block;
  margin: 14px 0 8px;
  font-size: 34px;
  color: var(--primary-dark);
  font-variant-numeric: tabular-nums;
}
.analysis-kpi small {
  font-size: 14px;
  margin-left: 8px;
  font-weight: 500;
}
.analysis-kpi p {
  color: var(--text-secondary);
  font-size: 13px;
}
.analysis-issue-table td {
  padding: 12px 8px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--text);
}
.analysis-issue-table button {
  background: transparent;
  border: 0;
  color: var(--primary-dark);
  text-align: left;
  cursor: pointer;
}
.analysis-issue-table .is-located {
  background: var(--primary-soft);
}
.analysis-issue-table {
  font-variant-numeric: tabular-nums;
}
.pending-label {
  color: #687c70;
  background: #f1f5f2;
  padding: 3px 8px;
  border-radius: 4px;
  white-space: nowrap;
}
.analysis-issue-table tbody {
  display: table-row-group;
}
.analysis-split:has(.analysis-issue-table) > .analysis-panel {
  max-height: 800px;
  overflow: auto;
}
.analysis-split:has(.analysis-issue-table) .analysis-stack {
  position: sticky;
  top: 20px;
  align-self: start;
}
.analysis-rank {
  max-height: 470px;
  overflow-y: auto;
}
.analysis-comparison-chart select {
  border: 1px solid var(--border);
  background: #fff;
  padding: 8px;
  border-radius: 6px;
  color: var(--text);
}

.analysis-page {
  display: grid;
  gap: 18px;
}
.analysis-context {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
  color: var(--text-secondary);
  font-size: 13px;
}
.analysis-context select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: var(--text);
}
.analysis-split {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(300px, 1fr);
  gap: 18px;
}
.analysis-split.spatial {
  grid-template-columns: minmax(0, 1fr) 360px;
}
.analysis-main-map {
  min-height: 650px;
}
.analysis-main-map :deep(.map-view) {
  height: 100%;
}
.analysis-stack {
  display: grid;
  gap: 18px;
  align-content: start;
  min-width: 0;
}
.analysis-stack :deep(.chart-panel) {
  height: 300px;
}
.analysis-stack :deep(.chart-canvas) {
  min-height: 210px;
}
.analysis-panel {
  padding: 22px;
  min-width: 0;
}
.analysis-panel h2 {
  font-size: 17px;
  font-weight: 650;
  margin: 0 0 8px;
  color: var(--text);
}
.analysis-panel p {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.8;
  margin: 8px 0 16px;
}
.analysis-rank {
  list-style: none;
  padding: 0;
  margin: 16px 0 0;
}
.analysis-rank button {
  display: flex;
  justify-content: space-between;
  width: 100%;
  padding: 9px 0;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  text-align: left;
}
.analysis-rank button:hover,
.analysis-rank button:focus-visible {
  background: var(--primary-soft);
  color: #16644f;
}
.analysis-tabs {
  display: flex;
  gap: 8px;
  margin: 16px 0;
}
.analysis-tabs button {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: var(--text-secondary);
}
.analysis-tabs .active {
  background: var(--primary-soft);
  border-color: var(--border-strong);
  color: var(--primary-dark);
}
.analysis-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}
.analysis-two-up {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.analysis-small-map {
  height: 300px;
  overflow: hidden;
  border-radius: 8px;
}
.analysis-small-map:has(.city-map-shell) {
  height: auto;
  overflow: visible;
}
.analysis-small-map :deep(.map-view),
.analysis-plan-map :deep(.map-view) {
  height: 100%;
  min-height: 0;
}
.analysis-small-map :deep(.province-map) {
  min-height: 0;
}
.analysis-small-map :deep(.province-map-footer),
.analysis-small-map :deep(.province-map-header p),
.analysis-small-map :deep(.province-map-legend) {
  display: none;
}
.analysis-small-map :deep(.province-map-canvas) {
  inset: 75px 0 20px;
}
.analysis-small-map :deep(.province-map-header h2) {
  font-size: 14px;
}
.analysis-small-map :deep(.province-map-actions) {
  bottom: 24px;
}
.analysis-quadrants {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 460px;
  margin: 22px 0;
  border: 1px solid var(--border);
  background: #fafcfb;
}
.analysis-quadrants > span {
  padding: 22px;
  color: #6a7b70;
  border-bottom: 1px dashed #c7d9cd;
  border-right: 1px dashed #c7d9cd;
  font-size: 13px;
}
.analysis-quadrants > div {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 22px;
  text-align: center;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  white-space: nowrap;
}
.analysis-quadrants small {
  display: block;
  color: #64786b;
  font-size: 12px;
  margin-top: 8px;
}
.analysis-comparison-chart {
  height: 650px;
  min-height: 650px;
}
.analysis-comparison-chart :deep(.chart-canvas) {
  height: 560px;
  min-height: 560px;
}
.analysis-warning {
  padding: 12px 14px;
  border-left: 3px solid var(--warning);
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 13px;
}
.analysis-issue-table {
  width: 100%;
  border-collapse: collapse;
}
.analysis-issue-table th {
  text-align: left;
  padding: 14px 8px;
  background: #f1f6f2;
  color: var(--text);
  font-size: 13px;
}
.analysis-plan-map {
  height: 530px;
}
.analysis-plan > :last-child :deep(.analysis-slot) {
  min-height: 530px;
  border: 1px dashed #c8d9cf;
  box-shadow: none;
}
.analysis-panel summary {
  cursor: pointer;
  color: var(--primary-dark);
  font-size: 13px;
  margin: 18px 0;
}
.analysis-method {
  display: flex;
  gap: 18px;
  border-top: 1px solid var(--border);
  padding: 16px 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.analysis-method strong {
  white-space: nowrap;
  color: var(--text);
}
@media (max-width: 1200px) {
  .analysis-split.spatial {
    grid-template-columns: minmax(0, 1fr) 310px;
  }
}
@media (max-width: 900px) {
  .analysis-split,
  .analysis-split.spatial,
  .analysis-two-up,
  .analysis-metrics {
    grid-template-columns: 1fr;
  }
  .analysis-method {
    flex-direction: column;
    gap: 6px;
  }
}
</style>
