<script setup>
import { computed, ref, watch } from 'vue'
import { comparisonMetrics, comparisonOption } from '@/utils/analysis-charts'
import { regionalDistribution, sortRegions } from '@/utils/regional-statistics'
import { formatNumber } from '@/utils/format'
import ChartContainer from '@/components/ChartContainer.vue'
const props = defineProps({
  rows: { type: Array, default: () => [] },
  metric: { type: String, default: 'count' },
  loading: Boolean,
  scopeName: { type: String, default: '全省区县' },
})
const emit = defineEmits(['update:metric', 'select', 'hover'])
const ascending = ref(false),
  selected = ref([])
const definition = computed(
  () => comparisonMetrics.find((row) => row.key === props.metric) || comparisonMetrics[0],
)
const distribution = computed(() => regionalDistribution(props.rows, props.metric))
const sorted = computed(() => sortRegions(props.rows, props.metric, ascending.value))
const outliers = computed(
  () => new Map(distribution.value.outliers.map((row) => [row.code, row.direction])),
)
const compared = computed(() => sorted.value.filter((row) => selected.value.includes(row.code)))
const option = computed(() => comparisonOption(compared.value, definition.value, ''))
watch(
  () => props.rows,
  () => {
    selected.value = selected.value.filter((code) => props.rows.some((row) => row.code === code))
  },
)
function toggle(code) {
  selected.value = selected.value.includes(code)
    ? selected.value.filter((value) => value !== code)
    : selected.value.length < 4
      ? [...selected.value, code]
      : selected.value
}
const number = (value) => formatNumber(value, definition.value.precision)
</script>
<template>
  <section class="panel county-comparison" aria-label="区县比较与分布异常值">
    <header>
      <div>
        <h2>区县比较</h2>
        <p>{{ scopeName }} · 同一快照与样本口径</p>
      </div>
      <div class="county-actions">
        <label
          >比较指标<select :value="metric" @change="emit('update:metric', $event.target.value)">
            <option v-for="item in comparisonMetrics" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select></label
        ><label
          >排序<select v-model="ascending">
            <option :value="false">降序</option>
            <option :value="true">升序</option>
          </select></label
        >
      </div>
    </header>
    <template v-if="rows.length">
      <div class="distribution-summary">
        <span
          >有效区县 <b>{{ distribution.count }}</b></span
        ><span
          >Q1 <b>{{ number(distribution.q1) }}</b></span
        ><span
          >中位数 <b>{{ number(distribution.median) }}</b></span
        ><span
          >Q3 <b>{{ number(distribution.q3) }}</b></span
        ><span>单位 {{ definition.unit }}</span>
      </div>
      <p class="county-note">
        {{ distribution.status }}。线性插值分位数（位置=(n−1)×p）。分布异常不等于服务风险；*
        表示检索触及上限，样本可能不完整。缺失值不补零。
      </p>
      <div class="county-table-wrap">
        <table>
          <thead>
            <tr>
              <th>对比（最多4个）</th>
              <th>区县</th>
              <th>{{ definition.label }}（{{ definition.unit }}）</th>
              <th>分布标注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sorted" :key="row.code">
              <td>
                <input
                  type="checkbox"
                  :aria-label="`对比${row.name}`"
                  :checked="selected.includes(row.code)"
                  :disabled="!selected.includes(row.code) && selected.length >= 4"
                  @change="toggle(row.code)"
                />
              </td>
              <td>
                <button
                  @click="emit('select', row)"
                  @mouseenter="emit('hover', row.cityCode)"
                  @mouseleave="emit('hover', '')"
                >
                  {{ row.name }}{{ row.completenessWarning ? ' *' : '' }}
                </button>
              </td>
              <td>{{ number(row[metric]) }}</td>
              <td>{{ outliers.has(row.code) ? `${outliers.get(row.code)}分布异常` : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ChartContainer
        v-if="compared.length"
        title="所选区县对比"
        :subtitle="`${definition.label} · ${definition.unit} · 点击条形定位区县`"
        :option="option"
        @district-select="
          (code) =>
            emit(
              'select',
              rows.find((row) => row.code === code),
            )
        "
        @city-hover="(code) => emit('hover', code)"
        @city-leave="emit('hover', '')"
      />
      <p v-else class="county-note">选择2—4个区县可并排比较；点击区县名称定位其真实站点。</p>
    </template>
    <p v-else role="status">
      {{ loading ? '正在读取当前口径…' : '当前口径无可比较区县结果；请检查快照和筛选。' }}
    </p>
  </section>
</template>
<style scoped>
.county-comparison {
  padding: var(--space-5);
  margin-top: var(--space-5);
  min-width: 0;
}
header,
.county-actions,
.distribution-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
h2 {
  font-size: var(--type-section);
  margin: 0 0 var(--space-2);
}
header p,
.county-note {
  color: var(--text-secondary);
  font-size: var(--type-caption);
  line-height: 1.7;
}
.county-actions label {
  display: grid;
  gap: var(--space-1);
  font-size: var(--type-caption);
}
select {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 6px 10px;
  color: var(--text);
}
.distribution-summary {
  justify-content: flex-start;
  padding: var(--space-3);
  background: var(--primary-soft);
  font-size: var(--type-caption);
}
.county-table-wrap {
  max-height: 340px;
  overflow: auto;
  border: 1px solid var(--border);
  margin-bottom: var(--space-4);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--type-caption);
  font-variant-numeric: tabular-nums;
}
th,
td {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
th {
  position: sticky;
  top: 0;
  background: var(--surface);
  z-index: 1;
}
td button {
  background: transparent;
  border: 0;
  color: var(--primary-dark);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
  padding: 0;
}
input {
  width: 16px;
  height: 16px;
  accent-color: var(--primary-dark);
}
</style>
