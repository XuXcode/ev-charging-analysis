<script setup>
import { computed } from 'vue'
import { comparisonMetrics } from '@/utils/analysis-charts'
import { formatNumber } from '@/utils/format'
const props = defineProps({
  rows: { type: Array, default: () => [] },
  metric: { type: String, default: 'count' },
  selectedCode: String,
})
const emit = defineEmits(['update:metric', 'select', 'hover'])
const definition = computed(
  () => comparisonMetrics.find((item) => item.key === props.metric) || comparisonMetrics[0],
)
const sorted = computed(() => [...props.rows].sort((a, b) => b[props.metric] - a[props.metric]))
const maximum = computed(() => Math.max(0, ...sorted.value.map((row) => row[props.metric])))
</script>
<template>
  <section class="panel region-ranking">
    <h2>区县样本排行</h2>
    <div class="ranking-metrics" role="group" aria-label="区县排名指标">
      <button
        v-for="item in comparisonMetrics"
        :key="item.key"
        :class="{ active: metric === item.key }"
        :aria-pressed="metric === item.key"
        @click="emit('update:metric', item.key)"
      >
        {{ item.label }}
      </button>
    </div>
    <ol v-if="rows.length">
      <li v-for="(row, index) in sorted" :key="row.code">
        <button
          :class="{ selected: selectedCode === row.code }"
          @mouseenter="emit('hover', row.code)"
          @mouseleave="emit('hover', '')"
          @focus="emit('hover', row.code)"
          @blur="emit('hover', '')"
          @click="emit('select', row.code)"
        >
          <span class="rank-number">{{ index + 1 }}</span
          ><span class="rank-label">{{ row.name }}{{ row.completenessWarning ? ' *' : '' }}</span
          ><strong
            >{{ formatNumber(row[metric], definition.precision) }}
            <small>{{ definition.unit }}</small></strong
          ><i :style="{ width: (maximum ? (row[metric] / maximum) * 100 : 0) + '%' }" />
        </button>
      </li>
    </ol>
    <p v-else>区县分析快照待接入</p>
    <p class="rank-note">
      * 检索触及上限，样本可能不完整。点击区县定位站点与边界；POI样本指标非官方设施统计。
    </p>
  </section>
</template>
<style scoped>
.region-ranking {
  padding: 22px;
  min-width: 0;
}
h2 {
  margin: 0 0 14px;
  font-size: 17px;
  color: #243b35;
}
.ranking-metrics {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.ranking-metrics button {
  padding: 7px 9px;
  border: 1px solid #d5e1d9;
  border-radius: 5px;
  background: #fff;
  color: #52685c;
  font-size: 12px;
}
.ranking-metrics .active {
  background: #e7f2eb;
  color: #17624f;
  border-color: #b8d7c6;
}
ol {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 480px;
  overflow: auto;
}
li > button {
  position: relative;
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  padding: 14px 8px 17px;
  border: 0;
  background: transparent;
  color: #344c41;
  text-align: left;
}
li > button:hover,
li > button.selected {
  background: #edf6f0;
}
li i {
  position: absolute;
  left: 0;
  bottom: 2px;
  height: 3px;
  background: #8abca3;
  max-width: 100%;
}
.rank-number {
  color: #6a7d71;
  min-width: 18px;
}
.rank-label {
  flex: 1;
}
strong {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
small {
  font-weight: 400;
  font-size: 12px;
  color: #52685c;
}
.rank-note {
  font-size: 12px;
  line-height: 1.7;
  color: #52685c;
  margin: 16px 0 0;
}
</style>
