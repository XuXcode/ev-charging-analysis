<script setup>
import { computed, ref, watch } from 'vue'
import { download } from '@/utils/export'
import { analysisSummary } from '@/utils/analysis-summary'
import { useAnalysisStore } from '@/stores/analysis'
import { snapshotProvenance } from '@/utils/analysis-provenance'
const analysis = useAnalysisStore(),
  copied = ref(false),
  error = ref('')
const metadata = computed(() => analysis.snapshot?.metadata)
const provenance = computed(() => snapshotProvenance(analysis.snapshot))
const time = computed(() =>
  metadata.value?.sourceUpdatedAt
    ? new Date(metadata.value.sourceUpdatedAt).toLocaleString('zh-CN', { hour12: false })
    : '待接入',
)
watch(
  () => [analysis.cityCode, analysis.districtCode, analysis.snapshot?.snapshotId],
  () => {
    copied.value = false
    error.value = ''
  },
)
function exportSnapshot() {
  if (!analysis.snapshot) return
  download(
    JSON.stringify(
      {
        scope: { cityCode: analysis.cityCode, districtCode: analysis.districtCode },
        snapshot: analysis.snapshot,
      },
      null,
      2,
    ),
    '空间分析快照.json',
    'application/json;charset=utf-8',
  )
}
async function copySummary() {
  error.value = ''
  copied.value = false
  try {
    const s = analysis.snapshot
    if (!s) return
    await navigator.clipboard.writeText(analysisSummary(s, analysis))
    copied.value = true
  } catch {
    error.value = '浏览器不允许复制，请从下方数据版本信息中选取。'
  }
}
</script>
<template>
  <section class="analysis-provenance" aria-label="分析数据来源与版本">
    <div>
      <strong>高德开放平台</strong><span>采集 {{ time }}</span
      ><span v-if="metadata">{{ metadata.algorithmVersion }}</span>
    </div>
    <div class="provenance-actions">
      <button :disabled="!metadata" @click="exportSnapshot">导出空间快照 JSON</button>
      <button :disabled="!metadata" @click="copySummary">
        {{ copied ? '摘要已复制' : '复制分析摘要' }}
      </button>
    </div>
    <details v-if="metadata">
      <summary>数据版本与方法</summary>
      <dl>
        <dt>基础采集批次</dt>
        <dd>{{ metadata.runId }}</dd>
        <dt>样本证据批次</dt>
        <dd>{{ metadata.qualityRunIds?.join(' / ') || metadata.runId }}</dd>
        <dt>待复核线索口径</dt>
        <dd>
          {{ metadata.filters?.needsReview ? '仅规则复核线索，与当前类别取交集' : '不限线索' }}
        </dd>
        <dt>冻结输入</dt>
        <dd>{{ metadata.frozenInputHash || '历史版本未冻结完整输入' }}</dd>
        <dt>分析快照</dt>
        <dd>{{ analysis.snapshot.snapshotId }}</dd>
        <dt>计算时间</dt>
        <dd>{{ analysis.snapshot.computedAt }}</dd>
        <dt>算法名称</dt>
        <dd>{{ provenance.algorithmName }}</dd>
        <dt>样本口径</dt>
        <dd>{{ provenance.filters }}</dd>
        <dt>算法参数</dt>
        <dd>{{ provenance.parameters }}</dd>
        <dt>范围与限制</dt>
        <dd>按当前类别与复核状态筛选POI；直线覆盖不等于道路可达性，非官方统计。</dd>
      </dl>
    </details>
    <p v-if="analysis.snapshot?.stale" class="provenance-warning" role="status">
      快照已过期，当前源数据发生变化，请运行分析任务更新。
    </p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.analysis-provenance {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  border-top: 1px solid var(--border);
  padding: var(--space-3) 0;
  font-size: var(--type-caption);
  color: var(--text-secondary);
}
.analysis-provenance > div:first-child {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.provenance-actions {
  margin-left: auto;
  display: flex;
  gap: var(--space-2);
}
.analysis-provenance button {
  border: 0;
  background: transparent;
  color: var(--primary-dark);
  min-height: 32px;
  padding: 4px 8px;
}
.analysis-provenance details {
  flex-basis: 100%;
}
.analysis-provenance summary {
  cursor: pointer;
}
.analysis-provenance dl {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 8px;
  line-height: 1.7;
}
.analysis-provenance dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.provenance-warning {
  color: var(--warning);
}
</style>
