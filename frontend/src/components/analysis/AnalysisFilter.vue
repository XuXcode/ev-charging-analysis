<script setup>
import { computed } from 'vue'
import { Cascader as ACascader } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useDashboardStore } from '@/stores/dashboard'
import { cityMapConfig } from '@/config/maps'
import { classificationLabels, reviewStatusLabels } from '@/config/analysis'
import { comparisonMetrics } from '@/utils/analysis-charts'
const analysis = useAnalysisStore(),
  dashboard = useDashboardStore(),
  route = useRoute(),
  router = useRouter()
const regionOptions = computed(() => [
  { value: '', label: '全省' },
  ...Object.values(cityMapConfig).map((city) => ({
    value: city.code,
    label: city.name,
    children: analysis.districtCatalog
      .filter((row) => row.cityCode === city.code)
      .map((row) => ({
        value: row.code,
        label: `${row.name}${row.completenessWarning ? ' *' : ''}`,
      })),
  })),
])
const regionPath = computed(() =>
  analysis.cityCode
    ? [analysis.cityCode, ...(analysis.districtCode ? [analysis.districtCode] : [])]
    : [''],
)
const batch = computed(() => dashboard.collectionInfo?.latestRun?.id)
const supplementBatch = computed(() => dashboard.collectionInfo?.latestSupplement?.id)
function changeRegion(path) {
  const [code = '', districtCode = ''] = path || []
  if (route.name === 'city') {
    const query = { ...route.query }
    delete query.district
    delete query.station
    if (districtCode) query.district = districtCode
    router.push({ path: code ? `/city/${code}` : '/', query })
  } else analysis.$patch({ cityCode: code, districtCode })
}
</script>
<template>
  <form class="analysis-filter" aria-label="统一分析筛选" @submit.prevent>
    <label class="region-select"
      >行政区域
      <a-cascader
        :value="regionPath"
        :options="regionOptions"
        change-on-select
        :allow-clear="false"
        placeholder="市州 / 区县"
        aria-label="市州与区县级联选择"
        @change="changeRegion"
      />
    </label>
    <label
      >POI类别<select v-model="analysis.classification">
        <option value="">全部样本 · 含待核验类别</option>
        <option v-for="(label, key) in classificationLabels" :key="key" :value="key">
          {{ label }}
        </option>
      </select></label
    >
    <label
      >复核状态<select v-model="analysis.reviewStatus">
        <option value="">全部状态</option>
        <option v-for="(label, key) in reviewStatusLabels" :key="key" :value="key">
          {{ label }}
        </option>
      </select></label
    >
    <label
      >数据批次<select v-model="analysis.batch">
        <option value="">当前数据集</option>
        <option v-if="batch" :value="batch">基础采集证据批次</option>
        <option v-if="supplementBatch" :value="supplementBatch">补采证据批次</option>
        <option
          v-if="analysis.batch && analysis.batch !== batch && analysis.batch !== supplementBatch"
          :value="analysis.batch"
        >
          指定批次
        </option>
      </select></label
    >
    <label
      >分析指标<select v-model="analysis.activeMetric">
        <option v-for="item in comparisonMetrics" :key="item.key" :value="item.key">
          {{ item.label }}
        </option>
      </select></label
    >
    <label
      class="review-scope"
      title="规则发现的名称或类别复核线索，与类别和人工状态取交集，不代表无效设施。"
      ><input v-model="analysis.needsReview" type="checkbox" />仅待复核线索 ·
      与当前类别取交集</label
    >
    <button
      type="button"
      @click="analysis.resetFilters(route.name === 'city' ? String(route.params.cityCode) : '')"
    >
      恢复默认
    </button>
  </form>
</template>
<style scoped>
.analysis-filter {
  display: flex;
  align-items: end;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: var(--space-4);
}
.region-select {
  min-width: 230px;
}
.review-scope {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 8px;
  color: var(--text-secondary);
}
label {
  display: grid;
  gap: 6px;
  color: var(--text-secondary);
  font-size: var(--type-caption);
}
select,
button {
  min-height: 36px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  color: var(--text);
  font: inherit;
}
button {
  margin-left: auto;
  color: var(--primary-dark);
  cursor: pointer;
}
select:disabled {
  opacity: 0.6;
}
</style>
