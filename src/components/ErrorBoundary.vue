<script setup>
import { ref, onErrorCaptured, watch } from 'vue'
import { useRoute } from 'vue-router'
import ViewState from './ViewState.vue'
const failed = ref(false),
  revision = ref(0),
  route = useRoute()
onErrorCaptured(() => {
  failed.value = true
  return false
})
function retry() {
  failed.value = false
  revision.value++
}
watch(() => route.fullPath, retry)
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
