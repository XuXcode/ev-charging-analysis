<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import MonitorLayout from '@/components/layout/MonitorLayout.vue'
import { useLayoutStore } from '@/stores/layout'
import { cityMapConfig } from '@/config/maps'
import { cityModules } from '@/config/topics'
import MapView from '@/components/MapView.vue'
import MetricCard from '@/components/MetricCard.vue'
import CollectionInfo from '@/components/CollectionInfo.vue'
import RegionRanking from '@/components/analysis/RegionRanking.vue'
import EmptyState from '@/components/EmptyState.vue'
import Loading from '@/components/Loading.vue'
import { formatNumber } from '@/utils/format'
import { analysisFilterQuery } from '@/utils/analysis-filters'
const store = useDashboardStore(),
  analysis = useAnalysisStore(),
  route = useRoute(),
  router = useRouter()
const layout = useLayoutStore()
const activeModule = ref('stations')
async function openAnalysis(key) {
  if (key === 'accessibility') {
    await router.push({
      path: '/analysis/accessibility',
      query: { ...analysisFilterQuery(analysis), travel_time: '10' },
    })
    return
  }
  activeModule.value = key
  layout.revealRight()
}
const city = computed(
  () =>
    store.cities.find((c) => c.code === route.params.cityCode) ||
    cityMapConfig[route.params.cityCode],
)
const districtQuery = computed(() =>
  typeof route.query.district === 'string'
    ? route.query.district
    : route.query.district
      ? 'invalid'
      : '',
)
const districts = computed(() =>
  analysis.districts.filter((row) => row.cityCode === city.value?.code),
)
const districtOptions = computed(() =>
  analysis.districtCatalog.filter((row) => row.cityCode === city.value?.code),
)
const district = computed(() =>
  districtOptions.value.find((row) => row.code === districtQuery.value),
)
const invalidDistrict = computed(() => districtQuery.value && analysis.snapshot && !district.value)
const cityMetrics = computed(() => analysis.cities.find((row) => row.code === city.value?.code))
const scope = computed(() =>
  districtQuery.value
    ? districts.value.find((row) => row.code === districtQuery.value)
    : cityMetrics.value,
)
const analysisLayer = computed(
  () =>
    ({ district: 'regions', heat: 'grid', coverage: 'coverage', uncovered: 'uncovered' })[
      activeModule.value
    ],
)
const metrics = computed(() => [
  {
    key: 'count',
    label: '高德可检索POI样本数量',
    value: scope.value?.count,
    unit: '条',
    precision: 0,
    pendingLabel: '分析快照待接入',
    change: '按供应方行政编码归属统计',
  },
  {
    key: 'density',
    label: 'POI样本密度',
    value: scope.value?.density,
    unit: '条/km²',
    precision: 3,
    pendingLabel: '分析快照待接入',
    change: '样本数量 / 行政边界模型面积',
  },
  {
    key: 'coverage',
    label: '1km直线样本覆盖率',
    value: scope.value?.coveragePercent,
    unit: '%',
    precision: 2,
    pendingLabel: '分析快照待接入',
    change: '合并缓冲区与行政边界面积交集',
  },
])
function selectDistrict(code) {
  if (code && !districtOptions.value.some((row) => row.code === code)) return
  const query = { ...route.query }
  delete query.station
  if (code) query.district = code
  else delete query.district
  router.push({ path: `/city/${city.value.code}`, query })
  store.hoverCity(code)
}
onMounted(() => analysis.load())
watch(
  () => route.params.cityCode,
  () => {
    activeModule.value = 'stations'
    store.hoverCity('')
  },
)
</script>
<template>
  <MonitorLayout
    scene="city"
    panel-eyebrow="市州 / 区县 · 真实站点"
    :panel-title="district?.name || city?.name || '市州详情'"
    panel-subtitle="高德POI样本 · 站点与空间结果分开读取"
  >
    <template #panel-actions
      ><button v-if="districtQuery" @click="selectDistrict('')">返回市州</button
      ><router-link to="/" class="back-link" @click="store.clearSelection()"
        >返回全省 ↗</router-link
      ></template
    >
    <template #map>
      <EmptyState
        v-if="!city"
        title="未找到该市州"
        description="请选择湖南省14市州中的有效行政编码。"
      />
      <EmptyState v-else-if="invalidDistrict" title="区县不属于当前市州"
        ><button @click="selectDistrict('')">返回市州</button></EmptyState
      >
      <Loading v-else-if="districtQuery && analysis.loading" />
      <EmptyState
        v-else-if="districtQuery && !district"
        title="区县边界快照暂不可用"
        description="无法验证区县范围，站点查询暂停。"
      />
      <MapView
        v-else-if="activeModule === 'stations'"
        :city-code="city.code"
        :district-code="district?.code || ''"
        @district-select="selectDistrict"
        @analysis-select="openAnalysis"
      />
      <MapView
        v-else-if="analysis.snapshot"
        :key="city.code + ':' + activeModule"
        :parent-code="city.code"
        :scope-code="district?.code || ''"
        :initial-layer="analysisLayer"
        :focus-code="district?.code || ''"
        analysis-layers
        :station-drilldown="false"
        selection-only
        @district-select="selectDistrict"
      />
      <EmptyState v-else title="当前图层快照待接入" description="没有可靠结果时不生成模拟结论。" />
    </template>
    <template v-if="city">
      <div class="module-tabs" role="group" aria-label="市州地图图层">
        <button
          :class="{ active: activeModule === 'stations' }"
          :aria-pressed="activeModule === 'stations'"
          @click="activeModule = 'stations'"
        >
          真实站点
        </button>
        <button
          v-for="module in cityModules"
          :key="module.key"
          :class="{ active: activeModule === module.key }"
          :aria-pressed="activeModule === module.key"
          @click="openAnalysis(module.key)"
        >
          {{ module.title }}
        </button>
      </div>
      <p v-if="analysis.error" class="city-quality-warning" role="alert">
        分析快照暂不可用：{{ analysis.error }} <button @click="analysis.load(true)">重试</button>
      </p>
      <p v-if="scope?.completenessWarning" class="city-quality-warning">
        检索触及上限，当前区域样本可能不完整。
      </p>
      <p v-if="analysis.snapshot?.stale" class="city-quality-warning">
        快照已过期，保留原批次结果，不与当前站点数量混算。
      </p>
      <div class="metric-grid">
        <MetricCard v-for="metric in metrics" :key="metric.key" :metric="metric" />
      </div>
      <RegionRanking
        :rows="districts"
        v-model:metric="analysis.activeMetric"
        :selected-code="district?.code"
        @select="selectDistrict"
        @hover="store.hoverCity"
      />
      <details v-if="analysis.snapshot">
        <summary>空间指标与分析口径</summary>
        <section class="city-result-detail">
          <h3>{{ district?.name || city.name }} · 样本口径</h3>
          <dl>
            <div>
              <dt>POI样本数量</dt>
              <dd>{{ formatNumber(scope?.count) }} 条</dd>
            </div>
            <div>
              <dt>占全省样本</dt>
              <dd>{{ formatNumber(scope?.sharePercent, 2) }}%</dd>
            </div>
            <div>
              <dt>行政边界模型面积</dt>
              <dd>{{ formatNumber(scope?.areaKm2, 1) }} km²</dd>
            </div>
            <div>
              <dt>1km样本覆盖面积</dt>
              <dd>{{ formatNumber(scope?.coveredAreaKm2, 1) }} km²</dd>
            </div>
            <div>
              <dt>样本未覆盖面积</dt>
              <dd>{{ formatNumber(scope?.uncoveredAreaKm2, 1) }} km²</dd>
            </div>
            <div>
              <dt>待复核线索</dt>
              <dd>{{ formatNumber(scope?.reviewCount) }} 条</dd>
            </div>
          </dl>
          <p>{{ scope?.qualityStatus }}</p>
          <p v-if="scope?.completenessWarning" class="city-quality-warning">
            检索触及上限，样本可能不完整。
          </p>
          <details>
            <summary>查看算法与指标说明</summary>
            <p v-for="item in analysis.snapshot?.indicatorDefinitions || []" :key="item.key">
              {{ item.label }}：{{ item.formula }}
            </p>
            <p>{{ analysis.snapshot.metadata.coordinateNotice }}</p>
            <p>所有保留POI参与计算，包含疑似停业、专用、个人和未知样本。</p>
            <p>网格为5km裁切网格；聚集图层使用有样本网格密度P95描述性阈值，不代表统计显著热点。</p>
            <p>
              快照 {{ analysis.snapshot.snapshotId }} · 算法
              {{ analysis.snapshot.metadata.algorithmVersion }} · 批次
              {{ analysis.snapshot.metadata.runId }}
            </p>
          </details>
        </section>
      </details>
      <details>
        <summary>数据来源与质量追溯</summary>
        <CollectionInfo />
      </details>
    </template>
  </MonitorLayout>
</template>
