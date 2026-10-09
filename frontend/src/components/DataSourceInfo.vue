<script setup>
import { useDashboardStore } from '@/stores/dashboard'
import AppIcon from './AppIcon.vue'
const store = useDashboardStore()
</script>
<template>
  <footer v-if="store.sourceInfo" class="data-source">
    <span
      ><AppIcon name="info" :size="14" />高德开放平台 · 入库POI样本与路线观测 · 非官方设施总量</span
    ><span>省、市州展示：DataV.GeoAtlas · 区县分析：高德行政区边界 · GCJ-02</span>
  </footer>
</template>
