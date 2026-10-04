<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { http } from '@/api/http'
import { formatNumber } from '@/utils/format'
// Independent source records, never a substitute for POI counts or missing statistics.
const result = ref(null),
  loading = ref(false),
  error = ref(''),
  page = ref(1)
const category = ref('official')
let abort,
  version = 0
async function load(nextPage = 1) {
  abort?.abort()
  abort = new AbortController()
  const current = ++version
  loading.value = true
  error.value = ''
  result.value = null
  page.value = nextPage
  try {
    const data = await http.get(`/statistics/${category.value}`, {
      params: { page: nextPage, page_size: 30 },
      signal: abort.signal,
    })
    if (current === version) result.value = data
  } catch (cause) {
    if (current === version && !abort.signal.aborted) error.value = cause.message
  } finally {
    if (current === version) loading.value = false
  }
}
onBeforeUnmount(() => {
  ++version
  abort?.abort()
})
</script>
<template>
  <section class="public-statistics">
    <div class="public-heading">
      <h3>官方 / 公开统计来源</h3>
      <button :disabled="loading" @click="load(1)">
        {{ loading ? '读取中…' : '查看已导入统计' }}
      </button>
    </div>
    <p>与POI样本独立记录。来源类别需核对原文；缺失年份或指标不推算，不补零。</p>
    <label
      >统计来源
      <select v-model="category" @change="load(1)">
        <option value="official">独立官方统计库</option>
        <option value="public">公开统计来源库</option>
      </select>
    </label>
    <p v-if="error" role="alert">{{ error }} <button @click="load(page)">重试</button></p>
    <template v-if="result">
      <p v-if="!result.total">尚未导入可靠统计文件，公共桩总量和历史趋势继续显示“—”。</p>
      <article v-for="row in result.items" :key="row.id">
        <strong
          >{{ row.adcode }} · {{ row.year }}年 · {{ row.label }} {{ formatNumber(row.value) }}
          {{ row.unit }}</strong
        >
        <p>{{ row.scopeDescription }}</p>
        <p>
          <a :href="row.sourceUrl" target="_blank" rel="noopener noreferrer"
            >{{ row.sourceName }} ↗</a
          >
          · {{ row.sourceKind === 'official' ? '官方来源标注' : '公开来源标注' }}
        </p>
        <details>
          <summary>导入追溯</summary>
          <p>文件 {{ row.fileName }} · 记录 {{ row.rowNumber }} · 导入 {{ row.importedAt }}</p>
          <p>文件 SHA256：{{ row.fileSha256 }}</p>
          <p>记录哈希：{{ row.recordHash }}</p>
        </details>
      </article>
      <div v-if="result.total > 30" class="public-pagination">
        <button :disabled="page <= 1 || loading" @click="load(page - 1)">上一页</button
        ><span>第{{ page }}页 / {{ Math.ceil(result.total / 30) }}页</span
        ><button :disabled="page * 30 >= result.total || loading" @click="load(page + 1)">
          下一页
        </button>
      </div>
      <p>{{ result.notice }}</p>
    </template>
  </section>
</template>
<style scoped>
.public-statistics {
  padding: 18px;
  background: #f6f9f6;
  border: 1px solid #dbe5df;
  border-radius: 6px;
  font-size: 13px;
  color: #52685c;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.public-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.public-heading h3 {
  margin: 0;
  font-size: 16px;
  color: #243b35;
}
button {
  border: 1px solid #cbded1;
  background: #fff;
  color: #17624f;
  padding: 6px 10px;
  border-radius: 5px;
}
article {
  padding: 16px 0;
  border-bottom: 1px solid #dbe5df;
}
strong {
  color: #243b35;
}
a,
summary {
  color: #17624f;
}
summary {
  cursor: pointer;
}
.public-pagination {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}
</style>
