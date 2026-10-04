<script setup>
import { onBeforeUnmount } from 'vue'
import { preparedDownload, clearPreparedDownload } from '@/utils/export'
onBeforeUnmount(clearPreparedDownload)
</script>
<template>
  <aside v-if="preparedDownload" class="export-notice" role="status" aria-label="导出文件已准备">
    <div><strong>导出文件已准备</strong><span>若浏览器未自动保存，可点击文件名下载。</span></div>
    <a :href="preparedDownload.url" :download="preparedDownload.filename">{{
      preparedDownload.filename
    }}</a>
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
.export-notice button {
  width: 36px;
  height: 36px;
  border: 0;
  background: var(--primary-soft);
  color: var(--primary-dark);
  cursor: pointer;
}
</style>
