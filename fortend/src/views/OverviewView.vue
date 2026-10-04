<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import { trendOption, comparisonOption } from '@/utils/charts'
import { cityMapConfig } from '@/config/maps'
import MetricCard from '@/components/MetricCard.vue'
import MapView from '@/components/MapView.vue'
import RankingList from '@/components/RankingList.vue'
import CollectionInfo from '@/components/CollectionInfo.vue'
import ChartContainer from '@/components/ChartContainer.vue'
import { formatNumber } from '@/utils/format'
import { coreFindings } from '@/utils/findings'
import { cityAnalysisRoute } from '@/utils/analysis-filters'
import AnalysisProvenance from '@/components/analysis/AnalysisProvenance.vue'
const findings = computed(() => coreFindings(analysis.snapshot))
const store = useDashboardStore()
const analysis = useAnalysisStore()
const router = useRouter()
const trendMetric = ref('piles')
const resultTab = ref('comparison')
const methodologyOpen = ref(false)
const sampleCities = computed(() =>
  Object.values(cityMapConfig).map((city) => ({
    ...city,
    ...analysis.cities.find((row) => row.code === city.code),
    samples: analysis.snapshot
      ? analysis.cities.find((row) => row.code === city.code)?.count
      : !analysis.classification &&
          !analysis.reviewStatus &&
          !analysis.needsReview &&
          !analysis.batch
        ? store.collectionInfo?.cities.find((row) => row.cityCode === city.code)?.storedCount
        : null,
  })),
)
const focusedCity = computed(() =>
  sampleCities.value.find((city) => city.code === store.hoveredCityCode),
)
const sampleDefinition = computed(() =>
  analysis.snapshot
    ? {
        ...analysis.definition,
        precision:
          analysis.activeMetric === 'density'
            ? 3
            : analysis.activeMetric === 'coveragePercent'
              ? 2
              : 0,
        description: analysis.definition.formula + '；米制近似、非官方统计。',
      }
    : {
        label: '高德可检索POI样本数',
        unit: '条',
        precision: 0,
        description: '已入库并通过清洗的高德可检索POI样本，不代表官方设施总量。',
      },
)
const trendChart = computed(() =>
  trendOption(
    store.analysisTrend,
    trendMetric.value,
    store.indicatorDefinitions.find((d) => d.key === trendMetric.value),
    store.analysisLabel,
    store.sourceInfo.simulated,
  ),
)
const compareChart = computed(() =>
  comparisonOption(
    sampleCities.value,
    analysis.snapshot ? analysis.activeMetric : 'samples',
    sampleDefinition.value,
    [],
    false,
  ),
)
const reservedChart = computed(() =>
  store.reservedCharts.find((item) => item.key === resultTab.value),
)
onMounted(() => store.selectCity(analysis.cityCode))
</script>
<template>
  <div class="overview-page">
    <div class="page-intro">
      <div>
        <h1>湖南省充电设施空间格局</h1>
        <p>省级专题地图 / 市州站点地图 · <span class="sample-data-badge">真实高德POI样本</span></p>
      </div>
      <div class="intro-actions">
        <span class="page-date">真实POI样本 · 非官方设施统计</span
        ><button class="methodology-button" @click="methodologyOpen = true">
          指标与分析口径 ↗
        </button>
      </div>
    </div>
    <div class="metric-grid">
      <MetricCard v-for="metric in store.metrics" :key="metric.key" :metric="metric" />
    </div>
    <div class="dashboard-grid">
      <section class="panel regional-panel sample-context-panel">
        <div class="panel-heading">
          <div>
            <h2>样本概况</h2>
            <p>省级看格局 · 市州看站点</p>
          </div>
        </div>
        <CollectionInfo />
        <div class="sample-context">
          <template v-if="focusedCity">
            <span class="sample-context-label">{{ focusedCity.name }}</span>
            <strong>{{ formatNumber(focusedCity.samples) }}<small>条 POI样本</small></strong>
            <p>
              占全省样本
              {{
                (analysis.snapshot?.province.count ?? store.collectionInfo?.storedCount) > 0
                  ? (
                      (focusedCity.samples /
                        (analysis.snapshot?.province.count ?? store.collectionInfo.storedCount)) *
                      100
                    ).toFixed(2) + '%'
                  : '—'
              }}
            </p>
          </template>
          <template v-else
            ><span class="sample-context-label">检索范围</span
            ><strong>{{ sampleCities.length }}<small>市州</small></strong>
            <p>悬停地图或右侧列表查看市州样本</p></template
          >
        </div>
        <div class="sample-method-note core-findings">
          <h3>核心发现</h3>
          <ol v-if="findings.length">
            <li v-for="fact in findings" :key="fact.key">
              <span>{{ fact.label }}</span>
              <p>{{ fact.text }}</p>
            </li>
          </ol>
          <p v-else>等待真实分析快照，当前不生成结论。</p>
        </div>
      </section>
      <MapView linked /><RankingList sample-mode />
    </div>
    <AnalysisProvenance />
    <div class="bottom-grid">
      <ChartContainer
        :title="`${store.analysisLabel}设施趋势`"
        :sample-based="false"
        :source="store.sourceInfo?.label"
        :subtitle="store.analysisTrend.length ? '季度末存量 · 已入库快照' : '历史统计待接入'"
        :empty="!store.analysisTrend.length"
        :option="trendChart"
        :description="`${store.analysisLabel}各季度充电设施存量${store.sourceInfo.simulated ? '，模拟数据' : ''}`"
      >
        <template #actions
          ><a-segmented
            v-model:value="trendMetric"
            size="small"
            :options="
              store.indicatorDefinitions
                .filter((d) => d.key !== 'density')
                .map((d) => ({ label: d.label, value: d.key }))
            "
            aria-label="趋势指标"
        /></template>
      </ChartContainer>
      <section class="panel comparison-workspace">
        <div class="analysis-chart-tabs" role="tablist" aria-label="对比分析图表">
          <button
            v-for="tab in store.reservedCharts"
            :key="tab.key"
            role="tab"
            :aria-selected="resultTab === tab.key"
            :class="{ active: resultTab === tab.key }"
            @click="resultTab = tab.key"
          >
            {{ tab.label }}<small v-if="tab.key !== 'comparison'">预留</small>
          </button>
        </div>
        <ChartContainer
          v-if="resultTab === 'comparison'"
          :loading="analysis.loading"
          :title="`市州${analysis.definition?.label || 'POI样本'}对比`"
          subtitle="按当前样本指标降序 · 虚线为14市州算术均值"
          :option="compareChart"
          :empty="!sampleCities.some((c) => Number.isFinite(c.samples))"
          :highlighted-codes="store.highlightedCodes"
          @city-hover="store.hoverCity"
          @city-leave="store.hoverCity()"
          @city-select="(code) => router.push(cityAnalysisRoute(analysis, code))"
        >
          <template #actions
            ><span class="chart-scope"
              >{{ analysis.definition?.unit || '条' }} · 非官方统计</span
            ></template
          >
        </ChartContainer>
        <div v-else class="reserved-chart-state" role="tabpanel">
          <span class="reserved-status">等待分析数据</span>
          <h2>{{ reservedChart?.title }}</h2>
          <p>{{ reservedChart?.description }}</p>
          <small>所需数据：{{ reservedChart?.required }}</small>
        </div>
      </section>
    </div>
    <Modal v-model:open="methodologyOpen" title="指标与分析口径" :footer="null" :width="640">
      <div class="methodology-content">
        <p v-if="store.sourceInfo.simulated" class="methodology-notice">
          当前为模拟数据。以下口径用于统一前端展示，不代表正式统计结果。
        </p>
        <dl>
          <template v-if="analysis.snapshot"
            ><dt>正式样本分析快照</dt>
            <dd>
              批次：{{ analysis.snapshot.metadata.runId }}；算法：{{
                analysis.snapshot.metadata.algorithmVersion
              }}。{{ analysis.snapshot.metadata.coordinateNotice }}
            </dd>
            <dt>样本覆盖口径</dt>
            <dd>
              {{
                analysis.snapshot.metadata.notice
              }}；1km缓冲合并后裁切，不重复累计重叠面积。热点为有样本网格密度P95描述性阈值，不是统计显著性检验。
            </dd>
            <template v-for="item in analysis.snapshot.indicatorDefinitions" :key="item.key"
              ><dt>{{ item.label }} · {{ item.unit }}</dt>
              <dd>{{ item.formula }}</dd></template
            ></template
          >
          <dt>高德可检索POI样本</dt>
          <dd>
            按现有真实入库样本计数，比例为市州样本数 /
            全省样本数。受收录范围、检索返回上限和分类质量影响，不能视为官方设施总量。
          </dd>
          <template v-for="definition in store.indicatorDefinitions" :key="definition.key"
            ><dt>
              {{ definition.label }} <small>{{ definition.unit }}</small>
            </dt>
            <dd>{{ definition.description }}</dd></template
          >
          <dt>同比 / 环比</dt>
          <dd>本期存量相对上年同季度 / 上季度的变化率。微趋势展示最近8个季度。</dd>
          <dt>市州均值</dt>
          <dd>仅在14市州当前指标齐全时显示算术均值；缺失数据不按零处理。密度均值未按面积加权。</dd>
          <dt>直流快充占比</dt>
          <dd>按市州公共充电桩数量加权汇总的直流快充占比。</dd>
          <dt>分组范围</dt>
          <dd v-for="group in store.groupDefinitions" :key="group.key">{{ group.description }}</dd>
        </dl>
        <div class="methodology-source">
          数据来源：{{ store.sourceInfo.label }}<br />边界来源：{{ store.sourceInfo.boundary
          }}<br />统计期：{{ store.sourceInfo.period }} · 更新：{{ store.sourceInfo.updatedAt }}
        </div>
      </div>
    </Modal>
  </div>
</template>
