<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { http } from '@/api/http'
import { useAnalysisStore } from '@/stores/analysis'
import MapView from '@/components/MapView.vue'
import { formatNumber } from '@/utils/format'
import { lowAccessibility } from '@/utils/planning'
const analysis = useAnalysisStore(),
  data = ref(null),
  error = ref(''),
  threshold = ref(15)
const controller = new AbortController()
const supported = computed(
  () =>
    analysis.classification === 'public_candidate' &&
    !analysis.reviewStatus &&
    !analysis.needsReview &&
    !analysis.batch,
)
const scoped = computed(() =>
  supported.value
    ? (data.value?.regions || []).filter(
        (r) =>
          (!analysis.cityCode || r.cityCode === analysis.cityCode) &&
          (!analysis.districtCode || r.adcode === analysis.districtCode),
      )
    : [],
)
const classified = computed(() => lowAccessibility(scoped.value, { minutes: threshold.value }))
const rows = computed(() => classified.value.low)
const unknown = computed(() => classified.value.unknown)
function locate(row) {
  analysis.$patch({ cityCode: row.cityCode, districtCode: row.adcode })
}
onMounted(async () => {
  try {
    data.value = await http.get('/analysis/accessibility/latest', { signal: controller.signal })
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause.message
  }
})
onBeforeUnmount(() => controller.abort())
</script>
<template>
  <div class="low-layout">
    <section class="panel low-panel">
      <h2>低可达性代表点清单</h2>
      <p>仅识别候选最短驾车时间超过阈值的区县代表点；没有真实需求数据时，不判定“高需求低供给”。</p>
      <label
        >道路时间阈值<select v-model.number="threshold">
          <option :value="5">5分钟</option>
          <option :value="10">10分钟</option>
          <option :value="15">15分钟</option>
        </select></label
      >
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="!supported">当前治理口径未生成对应道路观测，不回退其他口径。</p>
      <p v-if="data && supported">
        {{ rows.length }}个代表点超过阈值；{{
          unknown.length
        }}个起点观测缺失或无有效路线，单独待核验。
      </p>
      <div class="low-table">
        <table>
          <thead>
            <tr>
              <th>区县代表点</th>
              <th>候选最短时间</th>
              <th>对应道路距离</th>
              <th>样本质量</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.adcode">
              <td>
                <button @click="locate(row)">{{ row.name }}</button>
              </td>
              <td>{{ formatNumber(row.durationSeconds / 60, 1) }}分钟</td>
              <td>{{ formatNumber(row.distanceM / 1000, 2) }}km</td>
              <td>{{ row.completenessWarning ? '检索完整性警告' : '营业状态待核验' }}</td>
            </tr>
            <tr v-if="data && !rows.length">
              <td colspan="4">当前完整观测中没有超过所选阈值的代表点；不代表不存在服务问题。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <aside class="panel low-panel">
      <h2>定位与判断依据</h2>
      <p>点击清单切换对应区县高德地图，查看真实站点。</p>
      <MapView
        v-if="analysis.districtCode"
        :city-code="analysis.cityCode"
        :district-code="analysis.districtCode"
        compact
      />
      <p v-else>选择区县后展示站点定位地图。</p>
      <h3>需求与服务能力待接入</h3>
      <p>
        代表点不代表整个区县，空间邻近的3个站点不保证道路全局最近。容量、桩数、功率和等待时间缺失，当前不作排队或容量短缺判断。
      </p>
      <details v-if="data">
        <summary>道路观测追溯</summary>
        <p>{{ data.id }} · {{ data.algorithmVersion }}</p>
        <p>高德路径规划API · {{ data.updatedAt }}</p>
        <p>{{ data.notice }}</p>
      </details>
    </aside>
  </div>
</template>
<style scoped>
.low-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(340px, 1fr);
  gap: 16px;
}
.low-panel {
  padding: 24px;
}
.low-table {
  max-height: 650px;
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  text-align: left;
  padding: 14px 8px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
}
th {
  position: sticky;
  top: 0;
  background: var(--surface);
}
button {
  border: 0;
  background: transparent;
  color: var(--primary-dark);
  cursor: pointer;
  font: inherit;
}
select {
  margin: 0 10px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.low-panel p {
  line-height: 1.8;
}
@media (max-width: 1100px) {
  .low-layout {
    grid-template-columns: 1fr;
  }
}
</style>
