<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { http } from '@/api/http'
import { formatNumber } from '@/utils/format'
import { statisticDifferences } from '@/utils/statistics-differences'
const props = defineProps({
  adcode: String,
  metric: String,
  autoLoad: { type: Boolean, default: false },
  title: { type: String, default: '官方 / 公开统计来源' },
  emptyMessage: {
    type: String,
    default: '尚未导入可靠统计文件，公共桩总量和历史趋势继续显示“—”。',
  },
})
// Independent source records, never a substitute for POI counts or missing statistics.
const result = ref(null),
  loading = ref(false),
  error = ref(''),
  page = ref(1)
const category = ref('official')
const audit = ref(null),
  auditLoading = ref(false),
  auditError = ref('')
const differences = computed(() => statisticDifferences(audit.value?.records || []))
let auditAbort,
  auditVersion = 0
function clearAudit() {
  auditAbort?.abort()
  ++auditVersion
  audit.value = null
  auditError.value = ''
  auditLoading.value = false
}
async function compareSources() {
  clearAudit()
  const current = auditVersion
  const controller = new AbortController()
  auditAbort = controller
  auditLoading.value = true
  try {
    const sources = await Promise.all(
      ['official', 'public'].map((kind) =>
        http.get(`/statistics/${kind}`, {
          params: { page: 1, page_size: 100, adcode: props.adcode, metric: props.metric },
          signal: controller.signal,
        }),
      ),
    )
    if (current === auditVersion)
      audit.value = {
        records: sources.flatMap((source) => source.items),
        partial: sources.some((source) => source.total > source.items.length),
      }
  } catch (cause) {
    if (current === auditVersion && !controller.signal.aborted) auditError.value = cause.message
  } finally {
    if (current === auditVersion) auditLoading.value = false
  }
}
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
      params: { page: nextPage, page_size: 30, adcode: props.adcode, metric: props.metric },
      signal: abort.signal,
    })
    if (current === version) result.value = data
  } catch (cause) {
    if (current === version && !abort.signal.aborted) error.value = cause.message
  } finally {
    if (current === version) loading.value = false
  }
}
onMounted(() => {
  if (props.autoLoad) load(1)
})
watch(
  () => [props.adcode, props.metric],
  () => {
    clearAudit()
    if (props.autoLoad || result.value || loading.value) load(1)
  },
)
onBeforeUnmount(() => {
  clearAudit()
  ++version
  abort?.abort()
})
</script>
<template>
  <section class="public-statistics">
    <div class="public-heading">
      <h3>{{ title }}</h3>
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
    <div class="source-audit-actions">
      <button :disabled="auditLoading" @click="compareSources">
        {{ auditLoading ? '核对中…' : '核对同年来源' }}
      </button>
      <span>官方与公开记录分别保留，不自动合并口径。</span>
    </div>
    <p v-if="auditError" role="alert">
      {{ auditError }} <button @click="compareSources">重试核对</button>
    </p>
    <section v-if="audit" class="source-differences" aria-label="统计来源数值核对">
      <p v-if="audit.partial" role="status">仅核对每类来源前100条，当前结果不代表全部记录。</p>
      <p v-if="!differences.length">
        已读取的同年同指标记录未发现不同数值；这不证明统计口径一致或资料完整。
      </p>
      <div
        v-for="item in differences"
        :key="`${item.adcode}-${item.year}-${item.metric}-${item.unit}`"
      >
        <h4>{{ item.year }}年 · {{ item.label }} · 来源数值待核对</h4>
        <p>{{ item.notice }}</p>
        <ul>
          <li v-for="record in item.records" :key="`${record.sourceKind}-${record.id}`">
            <strong>{{ formatNumber(record.value) }} {{ record.unit }}</strong>
            · {{ record.sourceKind === 'official' ? '官方' : '公开' }} ·
            <a :href="record.sourceUrl" target="_blank" rel="noopener noreferrer"
              >{{ record.sourceName }} ↗</a
            >
            <details>
              <summary>查看统计口径与时点</summary>
              <p>{{ record.scopeDescription }}</p>
            </details>
          </li>
        </ul>
      </div>
    </section>
    <p v-if="error" role="alert">{{ error }} <button @click="load(page)">重试</button></p>
    <template v-if="result">
      <p v-if="!result.total">{{ emptyMessage }}</p>
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
.source-audit-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.source-differences {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid #d6c79c;
  border-radius: 6px;
  background: #fffdf6;
  color: #51492d;
}
.source-differences h4 {
  margin: 12px 0 6px;
  font-size: 14px;
}
.source-differences ul {
  padding-left: 20px;
}
.source-differences li + li {
  margin-top: 12px;
}
</style>
