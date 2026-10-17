<script setup>
import { computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { topics } from '@/config/topics'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import MonitorLayout from '@/components/layout/MonitorLayout.vue'
import { cityMapConfig } from '@/config/maps'
import MapView from '@/components/MapView.vue'
import ChartContainer from '@/components/ChartContainer.vue'
import AnalysisProvenance from '@/components/analysis/AnalysisProvenance.vue'
import CountyComparison from '@/components/analysis/CountyComparison.vue'
import RoadAccessibility from '@/components/analysis/RoadAccessibility.vue'
import LowAccessibility from '@/components/analysis/LowAccessibility.vue'
import RegionalTypes from '@/components/analysis/RegionalTypes.vue'
import { formatNumber } from '@/utils/format'
import { cityAnalysisRoute } from '@/utils/analysis-filters'
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
    ['5', '10', '15'].includes(route.query.travel_time)
      ? `${route.query.travel_time}分钟`
      : '10分钟',
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
const locatedDistrict = computed({
  get: () => analysis.districtCode,
  set: (value) => {
    analysis.districtCode = value
  },
})
const chart = computed(() => comparisonOption(cityRows.value, metric.value, selected.value))
const curve = computed(() => coverageDistribution(districts.value))
const scatter = computed(() => {
  const option = densityCoverageOption(analysis.cities)
  return {
    ...option,
    grid: { left: 48, right: 24, top: 36, bottom: 48 },
    xAxis: { ...option.xAxis, nameLocation: 'middle', nameGap: 26 },
    yAxis: { ...option.yAxis, name: '覆盖率 (%)', nameGap: 12 },
  }
})
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
  <MonitorLayout
    v-if="topic"
    :scene="slug"
    :panel-eyebrow="selected ? cityMapConfig[selected]?.name : '湖南省 · 14市州'"
    :panel-title="topic.title"
    :panel-subtitle="topic.description"
  >
    <template #panel-actions
      ><router-link
        v-if="selected"
        :to="cityAnalysisRoute(analysis, selected, analysis.districtCode)"
        class="back-link"
        >查看市州站点 ↗</router-link
      ></template
    >
    <template #map>
      <MapView
        v-if="slug === 'accessibility' && locatedDistrict"
        :city-code="selected"
        :district-code="locatedDistrict"
        @district-select="(code) => (locatedDistrict = code)"
      />
      <MapView
        v-else-if="slug === 'spatial'"
        linked
        selection-only
        analysis-layers
        :parent-code="selected || '430000'"
        :focus-code="locatedDistrict"
        :scope-code="locatedDistrict"
        @city-select="focus"
        @district-select="(code) => (locatedDistrict = code)"
      />
      <MapView v-else-if="slug === 'differences'" linked selection-only @city-select="focus" />
    </template>
    <template v-if="slug === 'differences'" #workspace>
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
      <details class="analysis-extension">
        <summary>市州空间类型</summary>
        <RegionalTypes :rows="analysis.cities" :stale="analysis.snapshot?.stale" @select="focus" />
      </details>
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
    </template>
    <p v-if="analysis.loading" class="analysis-warning" role="status">
      正在读取当前筛选的分析快照…
    </p>
    <p v-else-if="analysis.error" class="analysis-warning" role="alert">
      分析快照暂不可用：{{ analysis.error }} <button @click="analysis.load(true)">重试</button>
    </p>
    <p v-if="store.collectionError" class="analysis-warning" role="alert">
      {{ store.collectionError }} <button @click="store.loadCollectionInfo()">重试</button>
    </p>
    <div class="analysis-page" :class="`topic-${slug}`">
      <template v-if="slug === 'spatial'"
        ><div v-if="scopeMetrics" class="analysis-metrics">
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
      </template>
      <template v-else-if="slug === 'accessibility'">
        <div class="analysis-tabs" role="group" aria-label="道路时间阈值">
          <button
            v-for="item in ['5分钟', '10分钟', '15分钟']"
            :key="item"
            :class="{ active: mode === item }"
            :aria-pressed="mode === item"
            @click="mode = item"
          >
            {{ item }}
          </button>
        </div>
        <p class="analysis-note">区县代表点的道路观测，不代表人口或面积覆盖；缺失观测单列。</p>
        <button v-if="locatedDistrict" class="back-link" @click="locatedDistrict = ''">
          ← 返回道路时间专题
        </button>
        <RoadAccessibility
          :minutes="parseInt(mode)"
          map-target="#gis-map-stage"
          :map-visible="!locatedDistrict"
        />
        <LowAccessibility
          :show-map="false"
          @update:minutes="mode = $event + '分钟'"
          v-if="
            analysis.classification === 'public_candidate' &&
            !analysis.reviewStatus &&
            !analysis.needsReview &&
            !analysis.batch
          "
          :minutes="parseInt(mode)"
        />
      </template>
      <template v-else-if="slug === 'differences'">
        <section class="panel analysis-panel">
          <h2>区域定位</h2>
          <p>点击地图或图表选择市州，保留当前筛选。</p>
          <div class="analysis-small-map">
            <MapView
              compact
              linked
              selection-only
              :station-drilldown="false"
              @city-select="focus"
            />
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
      </template>
      <footer class="analysis-method">
        <strong>数据与方法</strong
        ><span
          >高德可检索POI样本，不代表官方设施总量。*
          表示检索触及上限，样本可能不完整。1km为直线几何覆盖，非道路可达性。</span
        >
      </footer>
      <AnalysisProvenance v-if="slug !== 'accessibility'" />
    </div>
  </MonitorLayout>
</template>
<style scoped>
.analysis-page {
  min-width: 0;
}
.analysis-note {
  margin: 10px 0 14px;
}
.analysis-rank {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
}
.analysis-rank button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 9px 0;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #d5e2d880;
  text-align: left;
  color: var(--text);
  font-size: 13px;
}
.analysis-rank button:hover {
  color: var(--primary);
}
.analysis-rank strong {
  white-space: nowrap;
  font-size: 13px;
}
.analysis-method {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
