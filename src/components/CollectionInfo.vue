<script setup>
import { computed, ref, watch, defineAsyncComponent } from 'vue'
import { getPoiQualityAudit } from '@/api/quality'
import { auditMatchesSummary } from '@/utils/poiQuality'
import { Drawer } from 'ant-design-vue'
import { useDashboardStore } from '@/stores/dashboard'
import { formatNumber } from '@/utils/format'
const QualityManager = defineAsyncComponent(
  () => import('@/components/analysis/QualityManager.vue'),
)
const PublicStatisticsPanel = defineAsyncComponent(
  () => import('@/components/analysis/PublicStatisticsPanel.vue'),
)

const store = useDashboardStore()
const open = ref(false)
const managerOpen = ref(false)
const refreshing = ref(false)
const audit = ref(null)
const auditLoading = ref(false)
const auditError = ref('')
const summary = computed(() => store.collectionInfo)
const run = computed(() => summary.value?.latestRun)
const supplement = computed(() => summary.value?.latestSupplement)
const scopeNotice = computed(() =>
  (
    summary.value?.notice ||
    run.value?.notice ||
    'POI 样本来自供应方有界检索，不等同于湖南省官方充电设施总量。'
  ).replace(
    '桩数、历史趋势及空间分析暂无数据。',
    '采集接口不提供桩数、历史趋势或空间分析结果；样本分析另读持久化快照。',
  ),
)
const auditCurrent = computed(() => auditMatchesSummary(audit.value, summary.value))
watch(open, async (visible) => {
  if (!visible || auditLoading.value || audit.value) return
  auditLoading.value = true
  try {
    audit.value = await getPoiQualityAudit()
  } catch {
    auditError.value = '离线核验记录尚未生成或读取失败，实时采集记录仍可查看。'
  } finally {
    auditLoading.value = false
  }
})
const batchCities = computed(
  () => new Map((run.value?.cities || []).map((city) => [city.cityCode, city])),
)
const statusLabels = {
  pending: '等待采集',
  running: '采集中',
  blocked: '配置未就绪',
  failed: '采集中断',
  interrupted: '采集中断',
  completed: '本批次检索完成',
  completed_with_limits: '本批次检索完成 · 部分区县触及返回上限',
}
const qualityMetrics = [
  { key: 'rawCount', label: '原始记录' },
  { key: 'uniqueCount', label: '批次有效去重' },
  { key: 'duplicateCount', label: '重复记录' },
  { key: 'rejectedCount', label: '排除记录' },
]
const reasonLabels = {
  invalid_record: '记录结构异常',
  missing_identity: '缺少 POI 标识或名称',
  outside_requested_district: '位于检索区县之外',
  not_ev_charging_station: '非汽车充电站',
  invalid_fields_or_coordinates: '字段或坐标异常',
  implausible_hunan_coordinates: '坐标不在湖南合理范围',
  identity_conflict: '标识与位置冲突',
  existing_city_conflict: '已有记录市州冲突',
  source_conflict: '已有记录来源冲突',
}
const rejectionReasons = computed(() => {
  const totals = {}
  for (const city of run.value?.cities || []) {
    for (const [reason, count] of Object.entries(city.rejectionReasons || {})) {
      totals[reason] = (totals[reason] || 0) + count
    }
  }
  return Object.entries(totals).sort((a, b) => b[1] - a[1])
})
const cappedDistricts = computed(() => {
  const scopes = Object.values(run.value?.manifest?.scopes || {}).flat()
  const names = new Map(scopes.map((scope) => [scope.adcode, scope.name]))
  return (run.value?.cappedDistricts || []).map((adcode) => ({
    adcode,
    name: names.get(adcode) || adcode,
  }))
})
const count = (value) => (Number.isFinite(value) ? formatNumber(value) : '—')
const dateTime = (value) => {
  if (!value) return '尚未采集'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '更新时间待确认'
    : date.toLocaleString('zh-CN', { hour12: false })
}
async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await store.loadCollectionInfo()
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <section class="data-status-card" aria-label="充电设施 POI 样本数据状态">
    <div class="data-status-heading">
      <span>全省采集批次</span>
      <span class="data-status-source">高德开放平台</span>
    </div>
    <div v-if="store.collectionError" class="data-status-error" role="alert">
      <p>{{ store.collectionError }}</p>
      <button :disabled="refreshing" @click="refresh">
        {{ refreshing ? '读取中…' : '重新读取' }}
      </button>
    </div>
    <template v-else>
      <div class="data-status-numbers">
        <div>
          <span>有效 POI 样本</span>
          <strong>{{ count(summary?.storedCount) }}<small v-if="summary">条</small></strong>
        </div>
        <div>
          <span>本批次覆盖区县</span>
          <strong>{{ count(run?.finishedDistricts) }}<small v-if="run">个</small></strong>
        </div>
      </div>
      <p class="data-status-caption">高德可检索 POI 样本数量</p>
      <div class="data-status-footer">
        <span>采集更新 {{ summary ? dateTime(summary.updatedAt) : '读取中…' }}</span>
        <button :disabled="!summary" @click="open = true">
          查看数据质量 <span aria-hidden="true">↗</span>
        </button>
      </div>
    </template>
  </section>

  <Drawer
    v-model:open="open"
    title="POI 样本数据质量"
    width="min(720px, 100vw)"
    :destroy-on-close="true"
  >
    <div class="quality-drawer">
      <div class="quality-intro">
        <div>
          <h3>高德可检索充电设施 POI 样本</h3>
          <p>
            累计有效入库 {{ count(summary?.storedCount) }} 条 ·
            {{ summary?.coordinateSystem || 'GCJ-02' }}
          </p>
        </div>
        <button class="quality-refresh" :disabled="refreshing" @click="refresh">
          {{ refreshing ? '读取中…' : '刷新记录' }}
        </button>
      </div>
      <p v-if="store.collectionError" class="quality-error" role="alert">
        {{ store.collectionError }}
      </p>
      <button class="quality-refresh" @click="managerOpen = true">筛选复核样本 ↗</button>
      <dl class="quality-provenance">
        <div>
          <dt>数据来源</dt>
          <dd>高德开放平台 · Web Service API</dd>
        </div>
        <div>
          <dt>采集更新时间</dt>
          <dd>{{ dateTime(summary?.updatedAt) }}</dd>
        </div>
        <div>
          <dt>数据口径</dt>
          <dd>行政区关键词检索与矩形分片补采，经标识、名称和坐标清洗去重；样本不代表官方全量。</dd>
        </div>
      </dl>
      <template v-if="run">
        <div class="quality-section-heading">
          <h3>全省基础采集批次</h3>
          <span>{{ statusLabels[run.status] || run.status }}</span>
        </div>
        <div class="quality-totals">
          <div v-for="metric in qualityMetrics" :key="metric.key">
            <span>{{ metric.label }}</span
            ><strong>{{ count(run.totals?.[metric.key]) }}<small>条</small></strong>
          </div>
        </div>
        <p class="quality-explanation">
          批次有效去重数量与累计库内样本数量分别统计；本轮补采保留已有站点和历史记录。
        </p>
        <dl class="quality-provenance">
          <div>
            <dt>区县检索</dt>
            <dd>
              完成 {{ count(run.finishedDistricts) }} / 发现 {{ count(run.discoveredDistricts) }} 个
            </dd>
          </div>
          <div>
            <dt>返回上限</dt>
            <dd>{{ count(cappedDistricts.length) }} 个区县触及供应方检索上限</dd>
          </div>
          <div>
            <dt>开始时间</dt>
            <dd>{{ dateTime(run.startedAt) }}</dd>
          </div>
          <div>
            <dt>结束时间</dt>
            <dd>{{ run.finishedAt ? dateTime(run.finishedAt) : '尚未结束' }}</dd>
          </div>
          <div>
            <dt>批次编号</dt>
            <dd class="quality-run-id">{{ run.id }}</dd>
          </div>
        </dl>
        <p v-if="run.lastError" class="quality-error" role="status">{{ run.lastError }}</p>
      </template>
      <p v-else class="quality-explanation">尚无采集批次记录。</p>

      <section v-if="supplement" aria-label="自适应分片补采记录">
        <div class="quality-section-heading">
          <h3>区县分片补采</h3>
          <span>{{ statusLabels[supplement.status] || supplement.status }}</span>
        </div>
        <div class="quality-totals">
          <div>
            <span>补采原始记录</span
            ><strong>{{ count(supplement.quality?.rawCount) }}<small>条</small></strong>
          </div>
          <div>
            <span>新增去重样本</span
            ><strong>{{ count(supplement.quality?.insertedCount) }}<small>条</small></strong>
          </div>
          <div>
            <span>重复观察保留</span
            ><strong
              >{{ count(supplement.quality?.retainedDuplicateCount) }}<small>条</small></strong
            >
          </div>
          <div>
            <span>排除记录</span
            ><strong>{{ count(supplement.quality?.rejectedCount) }}<small>条</small></strong>
          </div>
        </div>
        <p class="quality-explanation">
          {{ supplement.quality?.queryDifference }}。{{ supplement.notice }}
        </p>
        <dl class="quality-provenance">
          <div>
            <dt>补采批次</dt>
            <dd class="quality-run-id">{{ supplement.id }}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ dateTime(supplement.updatedAt) }}</dd>
          </div>
          <div>
            <dt>处理分片</dt>
            <dd>{{ count(supplement.shardCount) }} 个</dd>
          </div>
        </dl>
        <div class="quality-table-wrap">
          <table class="quality-city-table">
            <thead>
              <tr>
                <th scope="col">区县</th>
                <th scope="col">补采前</th>
                <th scope="col">补采后</th>
                <th scope="col">新增</th>
                <th scope="col">完整性说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in supplement.districts" :key="row.adcode">
                <td>{{ row.name }}</td>
                <td>{{ count(row.beforeCount) }}</td>
                <td>{{ count(row.afterCount) }}</td>
                <td>+{{ count(row.addedCount) }}</td>
                <td>{{ row.completenessStatus }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <h3 class="quality-table-title">14 市州样本记录</h3>
      <div class="quality-table-wrap">
        <table class="quality-city-table">
          <thead>
            <tr>
              <th scope="col">市州</th>
              <th scope="col">累计入库</th>
              <th scope="col">批次原始</th>
              <th scope="col">批次去重</th>
              <th scope="col">排除</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="city in summary?.cities || []" :key="city.cityCode">
              <th scope="row">{{ city.name }}</th>
              <td>{{ count(city.storedCount) }}</td>
              <td>{{ count(batchCities.get(city.cityCode)?.rawCount) }}</td>
              <td>{{ count(batchCities.get(city.cityCode)?.uniqueCount) }}</td>
              <td>{{ count(batchCities.get(city.cityCode)?.rejectedCount) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="quality-explanation">表内数量单位：条。最新批次未检索的市州以“—”表示。</p>

      <template v-if="rejectionReasons.length">
        <h3 class="quality-table-title">排除原因</h3>
        <ul class="quality-reasons">
          <li v-for="[reason, total] in rejectionReasons" :key="reason">
            <span>{{ reasonLabels[reason] || reason }}</span
            ><b>{{ count(total) }} 条</b>
          </li>
        </ul>
      </template>
      <template v-if="cappedDistricts.length">
        <h3 class="quality-table-title">触及返回上限的区县</h3>
        <div class="quality-districts">
          <span
            v-for="district in cappedDistricts"
            :key="district.adcode"
            :title="district.adcode"
            >{{ district.name }}</span
          >
        </div>
      </template>
      <section class="quality-audit" aria-label="样本分类与状态核验">
        <div class="quality-section-heading">
          <h3 class="quality-table-title">样本分类与状态核验</h3>
          <span>离线只读快照</span>
        </div>
        <p v-if="auditLoading">正在读取核验记录…</p>
        <p v-else-if="auditError" class="quality-error">{{ auditError }}</p>
        <p v-else-if="audit && !auditCurrent" class="quality-error">
          核验记录与当前数据批次、数量或更新时间不一致，已隐藏旧快照数量；请重新生成核验记录。
        </p>
        <template v-else-if="auditCurrent">
          <p class="quality-explanation">
            核验时间 {{ dateTime(audit.generatedAt) }} · 对照当前
            {{ count(audit.stationCount) }} 条入库样本
          </p>
          <dl class="quality-provenance">
            <div>
              <dt>营业状态线索</dt>
              <dd>
                名称含暂停营业或已拆除：{{ count(audit.pausedOrRemovedUniqueCount) }} 条（去重）
              </dd>
            </div>
            <div>
              <dt>原始类别</dt>
              <dd>
                未含“充电站”：{{ count(audit.rawTypeNotChargingCount) }} 条；专用：{{
                  count(audit.rawDedicatedChargingCount)
                }}
                条；个人：{{ count(audit.rawPersonalChargingCount) }} 条
              </dd>
            </div>
            <div>
              <dt>限制开放线索</dt>
              <dd>
                名称含内部使用或限制开放：{{ count(audit.accessHints['内部使用或限制开放']) }} 条
              </dd>
            </div>
            <div>
              <dt>人工复核清单</dt>
              <dd>
                {{ count(audit.reviewUniqueCount) }} 条样本含复核线索；全部保留，不计为无效数量
              </dd>
            </div>
            <div>
              <dt>追溯完整性</dt>
              <dd>
                缺少追溯字段 {{ count(audit.missingTraceCount) }} 条；未关联原始记录
                {{ count(audit.unmatchedRawCount) }} 条
              </dd>
            </div>
            <div>
              <dt>边界与坐标</dt>
              <dd>
                {{ audit.boundary.featureCount }} 市州 · {{ audit.boundary.coordinateSystem }} ·
                {{ audit.boundary.providerComparison }}
              </dd>
            </div>
          </dl>
          <details class="quality-original-types">
            <summary>查看高德原始POI类别</summary>
            <div class="quality-table-wrap">
              <table class="quality-city-table">
                <thead>
                  <tr>
                    <th>原始类别 / 编码</th>
                    <th>样本数（条）</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in audit.rawTypes" :key="row.typeCode">
                    <th scope="row">
                      {{ row.type }}<small>{{ row.typeCode }}</small>
                    </th>
                    <td>{{ count(row.count) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
          <p class="quality-explanation">{{ audit.notice }}</p>
        </template>
        <p class="quality-explanation">
          入库类型为采集器统一分类，不能替代供应方原始类别。名称提示不证明实际营业状态，也不能据此推算公共充电设施数量。
        </p>
        <p class="quality-explanation">
          边界按供应方文档使用GCJ-02；几何完整性与在线版本一致不等于逐点实地配准。后续接入WGS84数据前需明确转换口径。
        </p>
      </section>
      <div class="quality-note">
        <strong>样本范围说明</strong>
        <p>
          {{ scopeNotice }}
        </p>
        <p>
          更新时间为本地采集入库时间。样本数量不代表官方设施总量；充电桩数量与建设趋势需另行接入可靠统计。样本空间分析使用对应批次快照，不能推算上述统计指标。
        </p>
      </div>
      <PublicStatisticsPanel />
    </div>
  </Drawer>
  <QualityManager v-model:open="managerOpen" />
</template>

<style scoped>
.data-status-card {
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
}
.data-status-heading,
.data-status-footer,
.quality-intro,
.quality-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.data-status-heading {
  font-size: 13px;
  font-weight: 600;
}
.data-status-source {
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}
.data-status-numbers {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 12px;
  margin-top: 15px;
}
.data-status-numbers > div > span {
  display: block;
  color: var(--muted);
  font-size: 12px;
}
.data-status-numbers strong {
  display: block;
  margin-top: 4px;
  font-size: 26px;
  white-space: nowrap;
  line-height: 1.3;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--primary-dark);
}
.data-status-numbers small {
  margin-left: 5px;
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}
.data-status-caption {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 11px;
}
.data-status-footer {
  flex-wrap: wrap;
  border-top: 1px solid var(--border);
  margin-top: 12px;
  padding-top: 11px;
}
.data-status-footer > span {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.6;
}
.data-status-footer button,
.data-status-error button,
.quality-refresh {
  border: 0;
  background: transparent;
  padding: 2px 0;
  font-size: 12px;
  color: var(--primary);
  cursor: pointer;
  white-space: nowrap;
}
.data-status-footer button:disabled,
.data-status-error button:disabled,
.quality-refresh:disabled {
  cursor: default;
  opacity: 0.55;
}
.data-status-footer button:focus-visible,
.data-status-error button:focus-visible,
.quality-refresh:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 4px;
}
.data-status-error {
  font-size: 12px;
  line-height: 1.6;
  padding-top: 10px;
}
.data-status-error p {
  margin: 0 0 8px;
}
.quality-drawer {
  color: var(--text);
  font-size: 13px;
  line-height: 1.7;
}
.quality-drawer h3 {
  margin: 0;
  font-size: 15px;
  color: var(--primary-dark);
  font-weight: 600;
}
.quality-intro {
  align-items: flex-start;
}
.quality-intro p {
  margin: 5px 0 0;
  color: var(--muted);
}
.quality-provenance {
  margin: 20px 0;
}
.quality-provenance > div {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 12px;
  padding: 5px 0;
}
.quality-provenance dt {
  color: var(--muted);
}
.quality-provenance dd {
  margin: 0;
}
.quality-run-id {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.quality-section-heading {
  border-top: 1px solid var(--border);
  padding-top: 20px;
  align-items: flex-start;
}
.quality-section-heading > span {
  color: var(--muted);
  font-size: 12px;
  text-align: right;
}
.quality-totals {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 16px;
  padding: 16px;
  background: var(--primary-soft);
  border-radius: var(--radius);
}
.quality-totals span {
  display: block;
  color: #52685b;
  font-size: 12px;
}
.quality-totals strong {
  display: block;
  font-size: 23px;
  font-weight: 650;
  color: var(--primary-dark);
  font-variant-numeric: tabular-nums;
}
.quality-totals small {
  font-size: 11px;
  font-weight: 400;
  margin-left: 4px;
}
.quality-explanation {
  color: var(--muted);
  font-size: 12px;
  margin: 8px 0 18px;
}
.quality-error {
  color: #9a5a31;
  background: #fbf5eb;
  padding: 10px 12px;
  border-radius: var(--radius);
  overflow-wrap: anywhere;
}
.quality-drawer .quality-table-title {
  margin: 24px 0 12px;
}
.quality-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.quality-city-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}
.quality-city-table th,
.quality-city-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.quality-city-table th:first-child {
  text-align: left;
}
.quality-city-table thead {
  background: #f4f7f3;
  color: #52685b;
}
.quality-city-table tbody th {
  font-weight: 400;
}
.quality-city-table tbody tr:last-child > * {
  border-bottom: 0;
}
.quality-reasons {
  list-style: none;
  padding: 0;
  margin: 0;
}
.quality-reasons li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 5px 0;
}
.quality-reasons b {
  font-weight: 500;
  white-space: nowrap;
}
.quality-districts {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.quality-districts span {
  padding: 3px 9px;
  border: 1px solid var(--border);
  background: #f5f7f3;
  border-radius: 3px;
  font-size: 12px;
}
.quality-note {
  padding: 14px;
  background: #f5f7f3;
  border-left: 3px solid #84a98d;
  margin-top: 24px;
  color: #52685b;
  font-size: 12px;
}
.quality-audit {
  margin-top: 24px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}
.quality-original-types summary {
  color: var(--primary-dark);
  cursor: pointer;
  margin: 14px 0;
}
.quality-original-types th {
  white-space: normal;
}
.quality-original-types th small {
  display: block;
  color: var(--muted);
}
.quality-note strong {
  color: var(--primary-dark);
  font-weight: 600;
}
.quality-note p {
  margin: 6px 0 0;
}
@media (max-width: 600px) {
  .quality-totals {
    grid-template-columns: repeat(2, 1fr);
  }
  .quality-section-heading {
    flex-wrap: wrap;
  }
  .quality-section-heading > span {
    text-align: left;
  }
  .quality-provenance > div {
    grid-template-columns: 88px minmax(0, 1fr);
    gap: 8px;
  }
}
</style>
