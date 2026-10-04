<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { Drawer } from 'ant-design-vue'
import { getQualityPois, getPoiReviewEvents } from '@/api/analysis'
import { classificationLabels, reviewStatusLabels } from '@/config/analysis'
import { useAnalysisStore } from '@/stores/analysis'
import { cityMapConfig } from '@/config/maps'
import { useRoute, useRouter } from 'vue-router'
const props = defineProps({ open: Boolean })
const emit = defineEmits(['update:open'])
const analysis = useAnalysisStore()
const route = useRoute(),
  router = useRouter()
const classification = computed({
    get: () => analysis.classification,
    set: (value) => {
      analysis.classification = value
    },
  }),
  reviewStatus = computed({
    get: () => analysis.reviewStatus,
    set: (value) => {
      analysis.reviewStatus = value
    },
  }),
  adcode = computed({
    get: () => analysis.districtCode || analysis.cityCode,
    set: (value) => {
      const cityCode = value ? value.slice(0, 4) + '00' : ''
      if (route.name === 'city' && cityCode !== route.params.cityCode) {
        const query = { ...route.query }
        if (value && !value.endsWith('00')) query.district = value
        else delete query.district
        router.push({ path: cityCode ? `/city/${cityCode}` : '/', query })
        return
      }
      analysis.$patch({
        cityCode,
        districtCode: value && !value.endsWith('00') ? value : '',
      })
    },
  }),
  keyword = ref(''),
  onlyReview = ref(true)
const page = ref(1),
  result = ref(null),
  loading = ref(false),
  error = ref('')
const pages = computed(() => Math.max(1, Math.ceil((result.value?.total || 0) / 30)))
const reviewHistory = ref({}),
  historyError = ref('')
let historyAbort
async function loadHistory(stationId) {
  historyAbort?.abort()
  const current = new AbortController()
  historyAbort = current
  historyError.value = ''
  try {
    const data = await getPoiReviewEvents(stationId, current.signal)
    if (!current.signal.aborted)
      reviewHistory.value = { ...reviewHistory.value, [stationId]: data.items }
  } catch (cause) {
    if (!current.signal.aborted) historyError.value = cause.message
  }
}
let abort,
  generation = 0
async function load(reset = false) {
  if (reset) page.value = 1
  const current = ++generation
  abort?.abort()
  abort = new AbortController()
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const data = await getQualityPois(
      {
        classification: classification.value || undefined,
        review_status: reviewStatus.value || undefined,
        adcode: adcode.value || undefined,
        batch: analysis.batch || undefined,
        keyword: keyword.value || undefined,
        needs_review: onlyReview.value ? true : undefined,
        all_records: !onlyReview.value,
        page: page.value,
        page_size: 30,
      },
      abort.signal,
    )
    if (current === generation) result.value = data
  } catch (failure) {
    if (current === generation) error.value = failure.message
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(
  () => [
    analysis.classification,
    analysis.reviewStatus,
    analysis.cityCode,
    analysis.districtCode,
    analysis.batch,
  ],
  () => {
    if (props.open) load(true)
  },
)
watch(
  () => props.open,
  (visible) => {
    if (visible) load(true)
    else {
      ++generation
      abort?.abort()
      historyAbort?.abort()
    }
  },
)
function turn(step) {
  page.value += step
  load()
}
onBeforeUnmount(() => {
  historyAbort?.abort()
  ++generation
  abort?.abort()
})
</script>
<template>
  <Drawer
    :open="open"
    title="POI样本质量管理"
    :width="1080"
    @update:open="emit('update:open', $event)"
  >
    <p v-if="historyError" role="alert">{{ historyError }}</p>
    <p class="quality-manager-note">
      保守分类与原始证据可追溯。公共候选不代表已确认营业；所有记录保留。默认查看原复核线索清单。
    </p>
    <form class="quality-filters" @submit.prevent="load(true)">
      <label
        >分类<select v-model="classification">
          <option value="">全部分类</option>
          <option v-for="(label, key) in classificationLabels" :key="key" :value="key">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >复核状态<select v-model="reviewStatus">
          <option value="">全部状态</option>
          <option v-for="(label, key) in reviewStatusLabels" :key="key" :value="key">
            {{ label }}
          </option>
        </select></label
      >
      <label
        >市州 / 区县<select v-model="adcode">
          <option value="">湖南省全部</option>
          <optgroup label="市州">
            <option
              v-for="city in Object.values(cityMapConfig)"
              :key="city.code"
              :value="city.code"
            >
              {{ city.name }}
            </option>
          </optgroup>
          <optgroup v-if="analysis.cityCode" label="当前市州区县">
            <option
              v-for="row in analysis.districtCatalog.filter(
                (row) => row.cityCode === analysis.cityCode,
              )"
              :key="row.code"
              :value="row.code"
            >
              {{ row.name }}
            </option>
          </optgroup>
        </select></label
      >
      <label>站点名称<input v-model="keyword" placeholder="名称关键词" maxlength="100" /></label>
      <label class="quality-check"><input v-model="onlyReview" type="checkbox" />仅复核线索</label
      ><button type="submit" :disabled="loading">筛选</button>
    </form>
    <p v-if="loading" role="status">读取质量记录…</p>
    <p v-else-if="error" role="alert" class="quality-manager-error">
      {{ error }} <button @click="load()">重试</button>
    </p>
    <template v-else-if="result"
      ><p class="quality-manager-count">
        符合筛选条件 {{ result.total.toLocaleString() }} 条 · {{ result.notice }}
      </p>
      <div class="quality-manager-table">
        <table>
          <thead>
            <tr>
              <th>站点 / POI ID</th>
              <th>分类 / 状态</th>
              <th>原始类别与复核原因</th>
              <th>行政区 / 完整性</th>
              <th>批次 / 规则</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in result.items" :key="row.stationId">
              <td>
                <strong>{{ row.name }}</strong
                ><small>{{ row.poiId }}</small>
              </td>
              <td>
                {{ classificationLabels[row.classification]
                }}<small
                  >{{ reviewStatusLabels[row.reviewStatus] }} ·
                  {{ row.confidence === 'evidence_only' ? '仅来源线索' : '证据不足' }}</small
                >
                <small v-if="row.reviewNote">{{ row.reviewNote }}</small>
                <button @click="loadHistory(row.stationId)">查看复核台账</button>
                <details v-if="reviewHistory[row.stationId]" class="quality-evidence" open>
                  <summary>复核 / 修正记录</summary>
                  <p v-if="!reviewHistory[row.stationId].length">尚无复核事件</p>
                  <article v-for="event in reviewHistory[row.stationId]" :key="event.id">
                    <strong>{{ event.createdAt }} · {{ event.kind }}</strong>
                    <p>{{ event.reason }}</p>
                    <small>操作来源：{{ event.actor }} · 事件哈希：{{ event.eventHash }}</small>
                    <pre>{{
                      JSON.stringify({ before: event.before, after: event.after }, null, 2)
                    }}</pre>
                  </article>
                </details>
              </td>
              <td>
                {{ row.evidence.rawType || '原始类别缺失'
                }}<small v-for="reason in row.reasons" :key="reason.label">{{
                  reason.label
                }}</small>
                <details class="quality-evidence">
                  <summary>查看原始类别证据</summary>
                  <dl>
                    <dt>原始名称</dt>
                    <dd>{{ row.evidence.name || row.name }}</dd>
                    <dt>原始类别编码</dt>
                    <dd>{{ row.evidence.rawTypeCode || '未提供' }}</dd>
                    <dt>证据规则</dt>
                    <dd>{{ row.rulesVersion }}</dd>
                  </dl>
                  <small
                    >现有接口提供的原始字段摘录；完整供应方响应保存在采集原始页，不据此判定营业状态。</small
                  >
                </details>
              </td>
              <td>
                {{ row.adcode
                }}<small :class="{ warning: row.completenessWarning }">{{
                  row.completenessWarning ? '触及检索上限，可能不完整' : '未触及上限，仍不保证完整'
                }}</small>
              </td>
              <td>
                <small>{{ row.runId }}</small
                ><small>{{ row.rulesVersion }}</small>
              </td>
            </tr>
            <tr v-if="!result.items.length">
              <td colspan="5">没有符合条件的质量记录。</td>
            </tr>
          </tbody>
        </table>
      </div>
      <nav class="quality-manager-pagination" aria-label="质量记录分页">
        <button :disabled="page <= 1" @click="turn(-1)">上一页</button
        ><span>{{ page }} / {{ pages }} 页 · 每页30条</span
        ><button :disabled="page >= pages" @click="turn(1)">下一页</button>
      </nav></template
    >
  </Drawer>
</template>
<style scoped>
.quality-manager-note {
  line-height: 1.8;
  font-size: 14px;
  color: var(--text);
  background: var(--primary-soft);
  padding: 14px 16px;
  border-radius: 6px;
}
.quality-evidence summary {
  color: var(--primary-dark);
  cursor: pointer;
  padding: var(--space-2) 0;
  min-height: 32px;
}
.quality-evidence dl {
  display: grid;
  gap: var(--space-1);
  margin: var(--space-2) 0;
}
.quality-evidence dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.quality-evidence dt {
  color: var(--text-secondary);
}
.quality-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin: 24px 0;
}
.quality-filters label {
  display: grid;
  gap: 7px;
  color: var(--text);
  font-size: 13px;
}
.quality-filters select,
.quality-filters input:not([type='checkbox']) {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text);
  background: var(--surface);
  min-width: 130px;
}
.quality-filters .quality-check {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 8px;
}
.quality-filters button,
.quality-manager-pagination button {
  border: 1px solid var(--border-strong);
  border-radius: 5px;
  padding: 8px 12px;
  background: var(--primary-soft);
  color: var(--primary-dark);
}
.quality-manager-count {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.quality-manager-table {
  overflow-x: auto;
}
.quality-manager-table table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
.quality-manager-table th {
  padding: 12px 10px;
  text-align: left;
  color: var(--text);
  background: var(--background);
  white-space: nowrap;
}
.quality-manager-table td {
  padding: 14px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  min-width: 140px;
  color: var(--text);
  line-height: 1.7;
}
.quality-manager-table small {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  overflow-wrap: anywhere;
  margin-top: 5px;
}
.quality-manager-table strong {
  font-weight: 600;
}
.quality-manager-table .warning,
.quality-manager-error {
  color: var(--warning);
}
.quality-manager-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  font-size: 13px;
  color: var(--text-secondary);
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.quality-manager-table pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
