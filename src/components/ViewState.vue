<script setup>
import { computed } from 'vue'
const props = defineProps({
  kind: { type: String, default: 'empty' },
  title: String,
  description: String,
  compact: Boolean,
})
defineEmits(['retry'])
const label = computed(
  () =>
    props.title ||
    {
      loading: '正在读取数据',
      skeleton: '正在读取数据',
      error: '数据读取失败',
      warning: '数据可能不完整',
      pending: '数据待接入',
      empty: '当前范围没有数据',
    }[props.kind] ||
    '暂无数据',
)
</script>
<template>
  <div
    class="view-state"
    :class="[kind, { compact }]"
    :role="kind === 'error' ? 'alert' : 'status'"
    :aria-busy="kind === 'loading' || kind === 'skeleton'"
  >
    <span
      v-if="kind === 'loading' || kind === 'skeleton'"
      class="state-progress"
      aria-hidden="true"
    />
    <strong>{{ label }}</strong>
    <p v-if="description">{{ description }}</p>
    <button v-if="kind === 'error'" @click="$emit('retry')">重试</button>
    <slot />
  </div>
</template>
<style scoped>
.view-state {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 180px;
  padding: var(--space-6);
  color: var(--text-secondary);
  text-align: center;
}
.view-state strong {
  font-size: var(--type-label);
  color: var(--text);
  font-weight: 600;
}
.view-state p {
  line-height: 1.7;
  max-width: 48ch;
}
.view-state.compact {
  min-height: 0;
  padding: var(--space-3);
}
.error {
  background: var(--danger-soft);
}
.warning {
  background: var(--warning-soft);
}
.view-state button {
  min-height: var(--button-height);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  padding: 6px 16px;
  color: var(--primary-dark);
  border-radius: var(--radius);
}
.state-progress {
  width: 32px;
  height: 4px;
  background: var(--primary);
  border-radius: 4px;
  animation: pulse 1s ease-in-out infinite alternate;
}
@keyframes pulse {
  to {
    opacity: 0.3;
    transform: scaleX(0.6);
  }
}
@media (prefers-reduced-motion: reduce) {
  .state-progress {
    animation: none;
  }
}
</style>
