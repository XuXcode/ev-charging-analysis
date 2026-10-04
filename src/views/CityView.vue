<script setup>
import { computed, ref, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import { cityMapConfig } from '@/config/maps'
import { cityModules } from '@/mock/topics'
import MapView from '@/components/MapView.vue'
import MetricCard from '@/components/MetricCard.vue'
import CollectionInfo from '@/components/CollectionInfo.vue'
import RegionRanking from '@/components/analysis/RegionRanking.vue'
import EmptyState from '@/components/EmptyState.vue'
import Loading from '@/components/Loading.vue'
import AppIcon from '@/components/AppIcon.vue'
import { formatNumber } from '@/utils/format'
import { analysisFilterQuery } from '@/utils/analysis-filters'
const store = useDashboardStore(),
  analysis = useAnalysisStore(),
  route = useRoute(),
  router = useRouter()
const activeModule = ref('district')
const modulePanel = ref(null)
async function openAnalysis(key) {
  if (key === 'accessibility') {
    await router.push({
      path: '/analysis/accessibility',
      query: { ...analysisFilterQuery(analysis), travel_time: '10' },
    })
    return
  }
  activeModule.value = key
  await nextTick()
  modulePanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
const currentModule = computed(() => cityModules.find((m) => m.key === activeModule.value))
const analysisLayer = computed(
  () =>
    ({ district: 'regions', heat: 'grid', coverage: 'coverage', gaps: 'uncovered' })[
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
  {
    key: 'piles',
    label: '公共充电桩统计数量',
    value: district.value ? null : city.value?.piles,
    unit: '个',
    precision: 0,
    change: '可靠统计口径 · 独立于POI样本',
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
    activeModule.value = 'district'
    store.hoverCity('')
  },
)
</script>
<template>
  <template v-if="city">
    <div class="page-intro">
      <div>
        <h1>
          {{ city.name
          }}<span class="heading-secondary">{{ district ? district.name : 'POI样本分析' }}</span>
        </h1>
        <p>
          行政代码：{{ district?.code || city.code }} · 真实站点与分析快照分开读取 · 非官方设施统计
        </p>
      </div>
      <div class="city-back-links">
        <button v-if="districtQuery" class="back-link" @click="selectDistrict('')">返回市州</button
        ><router-link
          :to="{
            path: '/',
            query: analysisFilterQuery({ ...analysis, cityCode: '', districtCode: '' }),
          }"
          class="back-link"
          @click="store.clearSelection()"
          ><AppIcon name="back" :size="17" />返回全省总览</router-link
        >
      </div>
    </div>
    <div class="city-scope-controls">
      <span v-if="analysis.snapshot"
        >计算时间：{{ new Date(analysis.snapshot.computedAt).toLocaleString('zh-CN') }}</span
      >
    </div>
    <p v-if="analysis.error" class="city-quality-warning" role="alert">
      分析快照暂不可用：{{ analysis.error }} <button @click="analysis.load(true)">重试</button>
    </p>
    <p v-if="scope?.completenessWarning" class="city-quality-warning">
      {{
        district ? district.name : city.name
      }}包含触及检索上限的区县，样本可能不完整；覆盖率不代表官方覆盖或真实营业服务。
    </p>
    <p v-if="analysis.snapshot?.stale" class="city-quality-warning" role="alert">
      当前快照与最新输入不同，需重新运行分析任务。以下结果保留原批次，不与实时站点数量混算。
    </p>
    <div class="metric-grid">
      <MetricCard v-for="metric in metrics" :key="metric.key" :metric="metric" />
    </div>
    <div class="city-layout">
      <EmptyState
        v-if="invalidDistrict"
        title="区县不属于当前市州"
        description="请从区县选择器或排行中选择有效行政区。"
        ><button @click="selectDistrict('')">返回市州范围</button></EmptyState
      >
      <Loading v-else-if="districtQuery && analysis.loading" />
      <EmptyState
        v-else-if="districtQuery && !district"
        title="区县边界快照暂不可用"
        description="无法验证区县范围，站点查询暂停。"
      />
      <MapView
        v-else
        :city-code="city.code"
        :district-code="district?.code || ''"
        @district-select="selectDistrict"
        @analysis-select="openAnalysis"
      />
      <aside class="city-analysis-sidebar">
        <CollectionInfo /><RegionRanking
          :rows="districts"
          v-model:metric="analysis.activeMetric"
          :selected-code="district?.code"
          @select="selectDistrict"
          @hover="store.hoverCity"
        />
      </aside>
    </div>
    <section ref="modulePanel" class="panel module-panel">
      <div class="panel-heading">
        <div>
          <h2>市州与区县专题结果</h2>
          <p>
            样本分布、网格聚集与1km直线覆盖；道路可达性查看区县代表点的真实驾车观测，供需与优化待接入。
          </p>
        </div>
        <span class="pending-chip">{{ analysis.snapshot ? '真实分析快照' : '快照待接入' }}</span>
      </div>
      <div class="module-tabs" role="tablist" aria-label="市州分析模块">
        <button
          v-for="module in cityModules"
          :id="`tab-${module.key}`"
          :key="module.key"
          role="tab"
          :aria-selected="activeModule === module.key"
          aria-controls="city-module-content"
          :class="{ active: activeModule === module.key }"
          @click="openAnalysis(module.key)"
        >
          {{ module.title }}
        </button>
      </div>
      <div id="city-module-content" role="tabpanel" :aria-labelledby="`tab-${activeModule}`">
        <Loading v-if="analysis.loading" />
        <EmptyState
          v-else-if="invalidDistrict"
          title="无效区县范围"
          description="返回市州范围后查看真实结果。"
        />
        <div v-else-if="analysisLayer && analysis.snapshot" class="city-result-layout">
          <MapView
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
              <p v-for="item in analysis.snapshot.indicatorDefinitions" :key="item.key">
                {{ item.label }}：{{ item.formula }}
              </p>
              <p>{{ analysis.snapshot.metadata.coordinateNotice }}</p>
              <p>所有保留POI参与计算，包含疑似停业、专用、个人和未知样本。</p>
              <p>
                网格为5km裁切网格；聚集图层使用有样本网格密度P95描述性阈值，不代表统计显著热点。
              </p>
              <p>
                快照 {{ analysis.snapshot.snapshotId }} · 算法
                {{ analysis.snapshot.metadata.algorithmVersion }} · 批次
                {{ analysis.snapshot.metadata.runId }}
              </p>
            </details>
          </section>
        </div>
        <EmptyState
          v-else
          :title="currentModule.title + '待接入'"
          description="尚无可靠输入或相关分析结果，本阶段不生成模拟结论。"
        />
      </div>
    </section>
  </template>
  <EmptyState v-else title="未找到该市州" description="请选择湖南省14个市州中的有效行政代码。"
    ><router-link to="/"><a-button type="primary">返回全省</a-button></router-link></EmptyState
  >
</template>
<style scoped>
.city-back-links,
.city-scope-controls {
  display: flex;
  gap: 18px;
  align-items: center;
  flex-wrap: wrap;
}
.city-back-links button {
  border: 0;
  background: transparent;
}
.city-scope-controls {
  margin: 0 0 18px;
  color: #52685c;
  font-size: 13px;
}
.city-scope-controls select {
  border: 1px solid #d5e1d9;
  border-radius: 6px;
  padding: 8px 12px;
  background: #fff;
  color: #243b35;
}
.city-quality-warning {
  background: #fbf6eb;
  color: #795c2e;
  border-left: 3px solid #b68c46;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
}
.city-analysis-sidebar {
  display: grid;
  gap: 16px;
  align-content: start;
  min-width: 0;
}
.city-result-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  padding: 20px;
}
.city-result-detail {
  font-size: 13px;
  line-height: 1.7;
  color: #52685c;
  min-width: 0;
  overflow-wrap: anywhere;
}
.city-result-detail h3 {
  color: #243b35;
  font-size: 16px;
}
.city-result-detail dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #edf1ee;
}
.city-result-detail dd {
  margin: 0;
  color: #17624f;
  font-weight: 600;
}
.city-result-detail summary {
  cursor: pointer;
  color: #17624f;
  margin-top: 18px;
}
.city-result-detail dt {
  margin: 0;
}
@media (max-width: 1000px) {
  .city-result-layout {
    grid-template-columns: 1fr;
  }
}
</style>
