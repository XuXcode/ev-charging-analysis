<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { preparedDownload, clearPreparedDownload, prepareCompatibleDownload } from '@/utils/export'
const busy = ref(false),
  error = ref('')
let controller
async function prepare() {
  controller?.abort()
  controller = new AbortController()
  const active = controller
  busy.value = true
  error.value = ''
  try {
    await prepareCompatibleDownload(active.signal)
  } catch (cause) {
    if (!active.signal.aborted) error.value = cause.message
  } finally {
    if (!active.signal.aborted) busy.value = false
  }
}
watch(
  () => preparedDownload.value?.url,
  () => {
    controller?.abort()
    busy.value = false
    error.value = ''
  },
)
onBeforeUnmount(() => {
  controller?.abort()
  clearPreparedDownload()
})
</script>
<template>
  <aside v-if="preparedDownload" class="export-notice" role="status" aria-label="导出文件已准备">
    <div><strong>导出文件已准备</strong><span>若浏览器未自动保存，可点击文件名下载。</span></div>
    <a :href="preparedDownload.url" :download="preparedDownload.filename">{{
      preparedDownload.filename
    }}</a>
    <a v-if="preparedDownload.compatibilityUrl" :href="preparedDownload.compatibilityUrl"
      >兼容附件下载 · 5分钟有效</a
    >
    <button
      v-else-if="/\.(csv|png)$/i.test(preparedDownload.filename)"
      :disabled="busy"
      @click="prepare"
    >
      {{ busy ? '正在准备…' : '准备兼容下载' }}
    </button>
    <span v-if="error" role="alert">{{ error }}</span>
    <button aria-label="关闭导出提示" @click="clearPreparedDownload">×</button>
  </aside>
</template>
<style scoped>
.export-notice {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1500;
  max-width: min(540px, calc(100vw - 48px));
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  padding: 16px;
  box-shadow: var(--shadow-overlay);
  border-radius: var(--radius);
  font-size: 14px;
}
.export-notice div {
  display: grid;
  gap: 6px;
  flex: 1;
}
.export-notice span {
  color: var(--text-secondary);
  font-size: 12px;
}
.export-notice a {
  color: var(--primary-dark);
  overflow-wrap: anywhere;
}
.export-notice button[aria-label='关闭导出提示'] {
  width: 36px;
  height: 36px;
  border: 0;
  background: var(--primary-soft);
  color: var(--primary-dark);
  cursor: pointer;
}
</style>

<style scoped>
.export-notice button:not([aria-label]) {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--border-strong);
  background: var(--primary-soft);
  color: var(--primary-dark);
  border-radius: var(--radius);
  cursor: pointer;
}
</style>
