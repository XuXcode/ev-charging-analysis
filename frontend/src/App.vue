<script setup>
import { onMounted } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisContext } from '@/composables/useAnalysisContext'
import Loading from '@/components/Loading.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ExportNotice from '@/components/ExportNotice.vue'
import { token } from '@/utils/chart-theme'
const store = useDashboardStore()
// Keeps the route query and the analysis store in sync for every page.
useAnalysisContext()
onMounted(() => {
  store.load()
  store.loadCollectionInfo()
})
function reload() {
  store.load()
  store.loadCollectionInfo()
}
</script>
<template>
  <a-config-provider
    :theme="{
      token: {
        colorPrimary: token('primary'),
        borderRadius: 6,
        fontFamily: 'Inter, Microsoft YaHei, sans-serif',
        colorText: token('text'),
      },
    }"
    ><a href="#main-content" class="skip-link">跳转到主要内容</a>
    <!-- Only the first paint blocks on the dashboard request. Every page then owns its own
         loading / empty / error states inside the monitor shell, so a stale or missing metric
         can never blank the whole workspace. -->
    <div v-if="store.loading && !store.loaded" class="app-fallback"><Loading /></div>
    <div v-else-if="store.error && !store.loaded" class="app-fallback">
      <EmptyState title="数据载入失败" :description="store.error"
        ><a-button type="primary" @click="reload">重新加载</a-button></EmptyState
      >
    </div>
    <ErrorBoundary v-else>
      <router-view />
    </ErrorBoundary>
    <ExportNotice
  /></a-config-provider>
</template>
