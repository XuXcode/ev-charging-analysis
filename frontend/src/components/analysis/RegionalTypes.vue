<script setup>
import { computed } from 'vue'
import { regionalTypes } from '@/utils/regional-types'
import { formatNumber } from '@/utils/format'
const props = defineProps({ rows: { type: Array, default: () => [] }, stale: Boolean })
const emit = defineEmits(['select'])
const result = computed(() => regionalTypes(props.rows))
</script>
<template>
  <section class="panel regional-types">
    <header>
      <h2>市州空间类型</h2>
      <span>同一快照 · 相对格局</span>
    </header>
    <p v-if="result.thresholds">
      以14市州有效指标的中位数划分：密度
      {{ formatNumber(result.thresholds.density, 4) }} 条/km²，1km直线样本覆盖率
      {{ formatNumber(result.thresholds.coveragePercent, 2) }}%。等于阈值归高组。
    </p>
    <p v-else>等待至少两个市州的有效密度与覆盖指标。</p>
    <p v-if="stale" role="status">快照已过期，以下保留原批次结果。</p>
    <div class="type-grid">
      <button
        v-for="row in result.items"
        :key="row.code"
        @click="emit('select', row.code)"
        :title="`${row.name}：密度${row.density}条/km²，覆盖率${row.coveragePercent}%`"
      >
        <strong>{{ row.name }}</strong
        ><span>{{ row.type }}</span
        ><small>{{ formatNumber(row.coveragePercent, 2) }}% · 直线样本覆盖</small>
      </button>
    </div>
    <p class="method">类型由真实指标自动计算，不代表供需、公共开放、营业状态或正式风险等级。</p>
  </section>
</template>
<style scoped>
.regional-types {
  padding: 24px;
  margin: 16px 0;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
header h2 {
  font-size: 18px;
  margin: 0;
}
header span,
.method {
  color: var(--text-secondary);
}
.type-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px;
}
.type-grid button {
  display: grid;
  gap: 8px;
  text-align: left;
  padding: 14px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 160ms;
}
.type-grid button:hover {
  background: var(--surface-tint);
}
.type-grid button:focus-visible {
  outline: 2px solid var(--primary-dark);
  outline-offset: 3px;
}
.type-grid span {
  color: var(--primary-dark);
  font-weight: 600;
}
.type-grid small {
  font-size: 12px;
}
@media (max-width: 1450px) {
  .type-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
@media (max-width: 800px) {
  .type-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (prefers-reduced-motion: reduce) {
  .type-grid button {
    transition: none;
  }
}
</style>
