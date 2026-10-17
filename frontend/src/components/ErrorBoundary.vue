<script setup>
import { ref, onErrorCaptured, watch } from 'vue'
import { useRoute } from 'vue-router'
import ViewState from './ViewState.vue'
const failed = ref(false),
  revision = ref(0),
  route = useRoute()
onErrorCaptured((error, instance, info) => {
  if (import.meta.env.DEV) console.error('[UI boundary]', error.message, info)
  failed.value = true
  return false
})
function retry() {
  failed.value = false
  revision.value++
}
// Filter selections are mirrored into the query string, so fullPath also changes
// while the user stays on the same page. Bumping `revision` there would recreate the
// whole route subtree: expanded <details> groups and scroll position would be lost and
// every ECharts instance torn down and rebuilt. Only reset when the route itself
// changes or when a caught error has to be cleared.
let mountedPath = route.path
watch(
  () => route.fullPath,
  () => {
    const pathChanged = route.path !== mountedPath
    mountedPath = route.path
    if (!failed.value && !pathChanged) return
    retry()
  },
)
</script>
<template>
  <ViewState
    v-if="failed"
    kind="error"
    title="页面暂时无法显示"
    description="已保留当前分析范围，请重试或切换其他页面。"
    @retry="retry"
  />
  <slot v-else :key="revision" />
</template>
