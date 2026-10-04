<script setup>
import { useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
defineProps({ value: { type: String, default: '430000' } })
const router = useRouter(),
  store = useDashboardStore()
function select(code) {
  if (code === '430000') store.clearSelection()
  router.push(code === '430000' ? '/' : `/city/${code}`)
}
</script>
<template>
  <a-select
    aria-label="选择市州"
    :value="value"
    class="city-selector"
    show-search
    option-filter-prop="label"
    :options="[
      { value: '430000', label: '湖南省 · 全省' },
      ...store.cities.map((c) => ({ value: c.code, label: c.name })),
    ]"
    @change="select"
  />
</template>
