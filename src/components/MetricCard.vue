<script setup>
import { computed } from 'vue'
import { formatNumber } from '@/utils/format'
const props = defineProps({ metric: { type: Object, required: true } })
const unavailable = computed(() => !Number.isFinite(props.metric.value))
const sparkPath = computed(() => {
  const values = props.metric.sparkline || []
  const min = Math.min(...values),
    span = Math.max(...values) - min || 1
  return values
    .map(
      (value, i) =>
        `${i ? 'L' : 'M'}${(i * 100) / Math.max(1, values.length - 1)},${30 - ((value - min) / span) * 25}`,
    )
    .join(' ')
})
const signed = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
const sparkEndY = computed(() => {
  const values = props.metric.sparkline || []
  const min = Math.min(...values),
    span = Math.max(...values) - min || 1
  return 30 - ((values.at(-1) - min) / span) * 25
})
</script>
<template>
  <article class="metric-card" :class="{ 'metric-unavailable': unavailable }">
    <div class="metric-label">
      {{ metric.label }}<span v-if="metric.sparkline?.length" class="metric-period">期末存量</span>
    </div>
    <div class="metric-main">
      <div class="metric-value">
        {{ unavailable ? '—' : formatNumber(metric.value, metric.precision ?? 1)
        }}<span v-if="Number.isFinite(metric.value)">{{ metric.unit }}</span>
      </div>
      <svg
        v-if="metric.sparkline?.length"
        class="metric-sparkline"
        viewBox="0 0 100 35"
        role="img"
        :aria-label="`${metric.label}最近8季度微趋势`"
      >
        <path :d="sparkPath" fill="none" stroke="currentColor" stroke-width="2" />
        <circle cx="100" :cy="sparkEndY" r="2.5" fill="currentColor" />
      </svg>
    </div>
    <div v-if="unavailable" class="metric-pending">
      {{ metric.pendingLabel || '统计数据待接入' }}
    </div>
    <div v-else-if="Number.isFinite(metric.yoy)" class="metric-trends">
      <span
        >同比 <b :class="{ negative: metric.yoy < 0 }">{{ signed(metric.yoy) }}</b></span
      ><span
        >环比
        <b :class="{ negative: metric.qoq < 0 }">{{
          Number.isFinite(metric.qoq) ? signed(metric.qoq) : '—'
        }}</b></span
      >
    </div>
    <div v-else class="metric-change">{{ metric.change }}</div>
  </article>
</template>

<style scoped>
.metric-unavailable .metric-value {
  color: #6c8073;
  font-size: 32px;
  font-weight: 500;
}
.metric-pending {
  margin-top: 9px;
  color: var(--muted);
  font-size: 12px;
}
</style>
