<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Modal } from 'ant-design-vue'
import { loadAMap } from '@/utils/amap'
import { mapInsets } from '@/utils/map-viewport'
import {
  getCustomPolicy,
  planCustomRoutes,
  queryCustomRoutes,
  searchCustomPlaces,
} from '@/api/custom-accessibility'
const canvas = ref(null)
const origin = ref(null)
const keyword = ref('')
const count = ref(3)
const result = shallowRef(null)
const selectedId = ref(null)
const policy = ref(null)
const suggestions = ref([])
const busy = ref(false)
const searching = ref(false)
const autocomplete = ref(false)
const error = ref('')
const mapError = ref('')
let AMap,
  map,
  overlays = [],
  initialView,
  timer,
  controller,
  revision = 0,
  disposed = false
const statuses = {
  no_route: '无可用驾车路线',
  geometry_missing: '未返回道路轨迹',
  invalid_response: '道路结果不完整',
  provider_error: '服务未返回路线',
}
const resolved = (s) => s.route?.status === 'ok' && s.route?.segments?.length
const minutes = (s) => (s.route.durationSeconds / 60).toFixed(1)
const distance = (s) => (s.route.distanceM / 1000).toFixed(2)
function clearOverlays() {
  overlays.forEach((o) => {
    o.off?.()
    o.setMap(null)
  })
  overlays = []
}
function draw() {
  if (!map || !AMap) return
  clearOverlays()
  if (!origin.value) return
  const start = new AMap.Marker({
    position: [origin.value.longitude, origin.value.latitude],
    title: `起点：${origin.value.name}`,
    label: { content: '起点', direction: 'top' },
    zIndex: 120,
  })
  overlays.push(start)
  for (const [index, station] of (result.value?.candidates || []).entries()) {
    const active = selectedId.value === station.id
    const marker = new AMap.Marker({
      position: station.position,
      title: station.name,
      label: { content: `${index + 1}${active ? ' · 当前路线' : ''}`, direction: 'top' },
      zIndex: active ? 115 : 110,
    })
    marker.on('click', () => {
      selectedId.value = station.id
    })
    overlays.push(marker)
    if (resolved(station)) {
      // One polyline per provider step: never bridge missing geometry with a straight line.
      for (const segment of station.route.segments) {
        overlays.push(
          new AMap.Polyline({
            path: segment,
            strokeColor: active ? '#1677ed' : '#73a9ed',
            strokeOpacity: active ? 0.95 : 0.36,
            strokeWeight: active ? 6 : 3,
            lineJoin: 'round',
            lineCap: 'round',
            zIndex: active ? 105 : 100,
            bubble: true,
          }),
        )
      }
    }
  }
  map.add(overlays)
}
function fitRoutes() {
  if (map && overlays.length) map.setFitView(overlays, true, mapInsets(canvas.value), 17)
}
function clearQuery() {
  revision++
  result.value = null
  origin.value = null
  keyword.value = ''
  suggestions.value = []
  selectedId.value = null
  error.value = ''
  controller?.abort()
  clearTimeout(timer)
  clearOverlays()
  if (map && initialView) map.setZoomAndCenter(initialView.zoom, initialView.center, true)
}
function choose(point, name = '地图选点', locate = false) {
  if (busy.value) return
  revision++
  if (!origin.value && map) initialView = { zoom: map.getZoom(), center: map.getCenter() }
  origin.value = { longitude: point[0], latitude: point[1], name }
  keyword.value = name === '地图选点' ? '' : name
  result.value = null
  selectedId.value = null
  suggestions.value = []
  error.value = ''
  draw()
  if (locate && map) map.setZoomAndCenter(Math.max(13, map.getZoom()), point, true)
}
async function search() {
  const term = keyword.value.trim()
  if (term.length < 2 || searching.value || busy.value) return
  controller?.abort()
  controller = new AbortController()
  const current = ++revision
  searching.value = true
  error.value = ''
  try {
    const data = await searchCustomPlaces(term, controller.signal)
    if (current !== revision || disposed) return
    suggestions.value = data.items
    if (!data.items.length) error.value = '未找到带坐标的地点，请换个关键词或在地图上选点'
  } catch (e) {
    if (e.name !== 'CanceledError' && !disposed) error.value = e.message
  } finally {
    searching.value = false
    if (!disposed)
      getCustomPolicy()
        .then((p) => {
          policy.value = p
        })
        .catch(() => {})
  }
}
function inputChanged() {
  clearTimeout(timer)
  controller?.abort()
  revision++
  suggestions.value = []
  if (autocomplete.value && keyword.value.trim().length >= 2) timer = setTimeout(search, 650)
}
async function query() {
  if (!origin.value || busy.value) return
  busy.value = true
  error.value = ''
  const current = revision
  const body = {
    origin: { ...origin.value },
    candidate_count: Number(count.value),
    max_api_calls: 0,
  }
  try {
    const plan = await planCustomRoutes(body)
    if (disposed || current !== revision) return
    if (!plan.candidates.length) {
      result.value = plan
      error.value = '20km范围内暂无公共候选POI，可重新选择起点'
      return
    }
    let allowed = 0
    if (plan.requiredCalls > 0) {
      if (!plan.policy.enabled || plan.requiredCalls > plan.policy.drivingRemaining) {
        error.value = '查询未启用或本地预算不足，仅展示已有缓存；缺失路线未请求高德'
      } else {
        const confirmed = await new Promise((resolve) => {
          Modal.confirm({
            title: '确认真实道路查询',
            content: `可复用 ${plan.cacheHits} 条缓存，最多新增 ${plan.requiredCalls} 次高德驾车请求。请确保账号免费额度充足；失败不自动重试。`,
            okText: '确认查询',
            cancelText: '仅看缓存',
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          })
        })
        if (confirmed) allowed = plan.requiredCalls
      }
    }
    if (disposed || current !== revision) return
    const data = await queryCustomRoutes({ ...body, plan_id: plan.planId, max_api_calls: allowed })
    if (disposed || current !== revision) return
    result.value = data
    policy.value = data.policy
    selectedId.value = data.candidates.find(resolved)?.id ?? data.candidates[0]?.id
    if (data.warning) error.value = data.warning
    draw()
    // Fitting is an explicit control. Querying or selecting a route never moves the camera.
  } catch (e) {
    if (!disposed && current === revision) error.value = e.message
  } finally {
    busy.value = false
  }
}
watch(selectedId, draw)
watch(count, () => {
  revision++
  result.value = null
  selectedId.value = null
  draw()
})
onMounted(async () => {
  getCustomPolicy()
    .then((p) => {
      policy.value = p
    })
    .catch((e) => {
      error.value = e.message
    })
  try {
    await nextTick()
    AMap = await loadAMap()
    if (disposed) return
    map = new AMap.Map(canvas.value, {
      center: [112.98, 28.19],
      zoom: 12,
      viewMode: '2D',
      dragEnable: true,
      jogEnable: false,
      animateEnable: false,
      resizeEnable: true,
    })
    map.addControl(new AMap.Scale({ position: 'LB', offset: new AMap.Pixel(16, 20) }))
    initialView = { zoom: map.getZoom(), center: map.getCenter() }
    map.on('click', (e) => choose([e.lnglat.getLng(), e.lnglat.getLat()]))
  } catch {
    mapError.value = '高德地图加载失败，请检查 JS Key、网络和域名配置'
  }
})
onBeforeUnmount(() => {
  disposed = true
  revision++
  clearTimeout(timer)
  controller?.abort()
  clearOverlays()
  map?.destroy()
})
</script>
<template>
  <Teleport defer to="#gis-map-stage">
    <div class="custom-driving-stage">
      <div ref="canvas" class="custom-driving-map" aria-label="自定义地点驾车路线地图"></div>
      <div class="custom-map-controls glass-surface" role="group" aria-label="驾车路线地图控件">
        <button aria-label="放大地图" @click="map?.zoomIn()">+</button>
        <button aria-label="缩小地图" @click="map?.zoomOut()">−</button>
        <button aria-label="查看全部驾车路线" @click="fitRoutes">⌖</button>
      </div>
      <p v-if="mapError" class="custom-map-error" role="alert">{{ mapError }}</p>
    </div>
  </Teleport>
  <section class="custom-driving-panel" aria-label="自定义地点驾车查询">
    <h2>从任意地点出发</h2>
    <p class="hint">
      搜索湖南省内地点，或单击地图设置起点。候选来自全省公共候选库，独立于区县统计筛选。
    </p>
    <div class="place-search">
      <input
        v-model="keyword"
        aria-label="高德地点搜索"
        placeholder="输入地点名称"
        maxlength="80"
        :disabled="busy"
        @input="inputChanged"
        @keydown.enter="search"
      /><button
        :disabled="searching || busy || keyword.trim().length < 2 || !policy?.enabled"
        @click="search"
      >
        {{ searching ? '搜索中…' : '搜索' }}
      </button>
    </div>
    <label class="hint"
      ><input v-model="autocomplete" type="checkbox" :disabled="!policy?.enabled" />
      自动补全（输入会消耗地点提示配额）</label
    >
    <ul v-if="suggestions.length" class="place-suggestions">
      <li v-for="(item, index) in suggestions" :key="index">
        <button :disabled="busy" @click="choose(item.position, item.name, true)">
          <strong>{{ item.name }}</strong
          ><span>{{ item.address }}</span>
        </button>
      </li>
    </ul>
    <div class="origin-summary">
      <span>驾车起点</span><strong>{{ origin?.name || '尚未选点' }}</strong
      ><small v-if="origin"
        >{{ origin.longitude.toFixed(6) }}, {{ origin.latitude.toFixed(6) }} · GCJ-02</small
      >
    </div>
    <div class="query-controls">
      <label
        >候选站点
        <select v-model="count" :disabled="busy">
          <option :value="3">3 个</option>
          <option :value="5">5 个</option>
        </select></label
      ><button class="primary" :disabled="!origin || busy" @click="query">
        {{ busy ? '正在查询道路…' : '查询驾车路线' }}
      </button>
    </div>
    <div class="query-controls">
      <button :disabled="busy || !origin" @click="clearQuery">清除并恢复视角</button
      ><button :disabled="!result?.candidates.length" @click="fitRoutes">查看全部路线</button>
    </div>
    <p v-if="error" class="query-warning" role="alert">{{ error }}</p>
    <p v-if="policy && !policy.enabled" class="query-warning">
      真实查询未启用。可选点并读取路线缓存，启用前请确认免费配额。
    </p>
    <div v-if="result" class="route-results">
      <div class="result-summary">
        <strong>{{ result.candidates.length }} 个公共候选站点</strong
        ><span>缓存 {{ result.cacheHits }} · 新请求 {{ result.apiCalls || 0 }}</span>
      </div>
      <button
        v-for="(station, index) in result.candidates"
        :key="station.id"
        class="route-station"
        :class="{ selected: selectedId === station.id }"
        :aria-pressed="selectedId === station.id"
        @click="selectedId = station.id"
      >
        <strong>{{ index + 1 }}. {{ station.name }}</strong
        ><span class="station-address">{{ station.address || '暂无地址' }}</span
        ><template v-if="resolved(station)"
          ><span class="route-metrics"
            ><b>{{ minutes(station) }}<small> 分钟</small></b
            ><span>{{ distance(station) }} km</span
            ><em v-if="station.id === result.candidates.find(resolved)?.id">已查询中最快</em></span
          ><span class="thresholds"
            ><span
              v-for="minute in [5, 10, 15]"
              :key="minute"
              :class="{ reachable: station.route.durationSeconds <= minute * 60 }"
              >{{ minute }}分钟
              {{ station.route.durationSeconds <= minute * 60 ? '可达' : '不可达' }}</span
            ></span
          ></template
        ><span v-else class="hint">{{
          statuses[station.route?.status] || '暂无道路轨迹，尚未调用高德'
        }}</span></button
      ><time class="hint" v-if="result.queriedAt"
        >本次查询 {{ new Date(result.queriedAt).toLocaleString('zh-CN') }}</time
      >
    </div>
    <details class="query-method">
      <summary>查询口径与调用说明</summary>
      <p>
        在现有真实POI库中筛选20km直线范围内最近的3或5个公共候选站点，仅用于候选筛选；道路时间、距离与蓝色轨迹均来自高德驾车结果。旧缓存缺少轨迹时需补查，不绘制直线替代路线。
      </p>
      <p>
        结果按候选驾车时间排序，不保证全库最快。5/10/15分钟为起点到站点的判断，不代表人口、面积覆盖或实时营业状态。与122区县代表点统计独立，不写入其快照。
      </p>
      <p>
        路线缓存有效期7天，地点提示6小时；失败计入上限，不自动重试。页面预算是本地安全上限，不等于高德账户剩余额度。
      </p>
      <p v-if="policy">
        本地今日剩余：驾车 {{ policy.drivingRemaining }} 次，地点提示
        {{ policy.placesRemaining }} 次（UTC日）。
      </p>
    </details>
  </section>
</template>
<style scoped>
.custom-driving-stage,
.custom-driving-map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.custom-driving-panel {
  display: grid;
  gap: 12px;
  color: #254f40;
}
.custom-driving-panel h2 {
  font-size: 18px;
  margin: 0;
}
.hint,
.station-address {
  font-size: 12px;
  line-height: 1.6;
  color: #506e61;
  margin: 0;
}
.place-search,
.query-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.place-search input {
  flex: 1;
  min-width: 120px;
  width: 0;
}
.custom-driving-panel input:not([type='checkbox']),
.custom-driving-panel select,
.custom-driving-panel button {
  border: 1px solid rgba(64, 119, 90, 0.23);
  border-radius: 9px;
  padding: 7px 10px;
  background: rgba(242, 251, 245, 0.65);
  color: inherit;
  font: inherit;
  font-size: 13px;
}
.custom-driving-panel button {
  cursor: pointer;
}
.custom-driving-panel button:disabled {
  cursor: default;
  opacity: 0.5;
}
.custom-driving-panel .primary {
  background: #1c775e;
  color: #fff;
}
.origin-summary {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-block: 1px solid rgba(87, 132, 107, 0.18);
}
.origin-summary > span,
.origin-summary small {
  font-size: 12px;
  color: #557466;
}
.query-controls {
  justify-content: space-between;
}
.query-warning {
  font-size: 12px;
  background: rgba(255, 244, 207, 0.8);
  padding: 10px;
  border-left: 2px solid #bc9b49;
  border-radius: 8px;
  margin: 0;
}
.place-suggestions {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow: auto;
}
.place-suggestions button {
  width: 100%;
  text-align: left;
  display: grid;
  gap: 4px;
}
.place-suggestions span {
  font-size: 12px;
}
.route-results {
  display: grid;
  gap: 8px;
}
.result-summary {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
.custom-driving-panel .route-station {
  display: grid;
  gap: 7px;
  text-align: left;
  padding: 12px;
  background: linear-gradient(135deg, rgba(233, 249, 239, 0.55), rgba(225, 244, 232, 0.25));
  border: 1px solid rgba(75, 134, 104, 0.16);
}
.custom-driving-panel .route-station.selected {
  border-color: #308b70;
  box-shadow: inset 3px 0 #2e8a6d;
}
.route-metrics {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: #195941;
}
.route-metrics b {
  font-size: 22px;
}
.route-metrics small {
  font-size: 12px;
  font-weight: 400;
}
.route-metrics em {
  font-size: 11px;
  font-style: normal;
  color: #1f719e;
}
.thresholds {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.thresholds > span {
  font-size: 11px;
  background: rgba(101, 120, 109, 0.1);
  border-radius: 20px;
  padding: 3px 6px;
  color: #647268;
}
.thresholds > span.reachable {
  background: rgba(38, 142, 97, 0.13);
  color: #226d4f;
}
.query-method {
  font-size: 12px;
  line-height: 1.8;
  border-top: 1px solid rgba(87, 132, 107, 0.2);
  padding-top: 10px;
}
.query-method summary {
  cursor: pointer;
}
.custom-map-error {
  position: absolute;
  top: 160px;
  left: 30%;
  background: #fff7df;
  padding: 16px;
  border-radius: 12px;
}
.custom-map-controls {
  position: absolute;
  right: var(--monitor-right-offset, 24px);
  bottom: 70px;
  display: grid;
  z-index: 130;
  border-radius: 12px;
  overflow: hidden;
}
.custom-map-controls button {
  width: 36px;
  height: 36px;
  border: 0;
  border-bottom: 1px solid rgba(70, 120, 95, 0.14);
  background: transparent;
  color: #285e49;
  font-size: 20px;
  cursor: pointer;
}
.custom-map-controls button:last-child {
  border-bottom: 0;
}
.custom-driving-stage :deep(.amap-marker-label) {
  border: 1px solid rgba(47, 117, 84, 0.4);
  border-radius: 7px;
  padding: 3px 6px;
  background: rgba(235, 250, 241, 0.9);
  color: #235d44;
  font-size: 12px;
}
</style>
