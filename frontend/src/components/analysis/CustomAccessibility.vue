<script setup>
import { computed, ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
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
const result = shallowRef(null)
const selectedId = ref(null)
const policy = ref(null)
const suggestions = ref([])
const busy = ref(false)
const searching = ref(false)
const autocomplete = ref(false)
const error = ref('')
const mapError = ref('')
const picking = ref(true)
const expandedId = ref(null)
const validRoutes = computed(() => (result.value?.candidates || []).filter(resolved))
const fastest = computed(() => validRoutes.value[0])
const withinTen = computed(
  () => validRoutes.value.filter((s) => s.route.durationSeconds <= 600).length,
)
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
    content: '<span class="access-map-pin is-origin">起</span>',
    offset: new AMap.Pixel(-15, -15),
    zIndex: 120,
  })
  overlays.push(start)
  for (const [index, station] of (result.value?.candidates || []).entries()) {
    const active = selectedId.value === station.id
    const marker = new AMap.Marker({
      position: station.position,
      title: station.name,
      content: `<span class="access-map-pin ${active ? 'is-destination' : ''}">${index + 1}</span>`,
      offset: new AMap.Pixel(-15, -15),
      zIndex: active ? 115 : 110,
    })
    marker.on('click', () => {
      selectedId.value = station.id
    })
    overlays.push(marker)
    if (active && resolved(station)) {
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
    candidate_count: 3,
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
      if (!plan.policy.enabled) {
        error.value = '查询尚未启用，仅展示已有缓存；缺失路线未请求高德'
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
    map.on('click', (e) => {
      if (picking.value) choose([e.lnglat.getLng(), e.lnglat.getLat()])
    })
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
  <section class="custom-driving-panel" aria-label="自定义地点驾车查询" :aria-busy="busy">
    <section class="access-block access-search-block">
      <label class="access-section-label" for="access-place">出发地点</label>
      <div class="place-search">
        <input
          id="access-place"
          v-model="keyword"
          aria-label="高德地点搜索"
          placeholder="搜索地点，或在地图选点"
          maxlength="80"
          :disabled="busy"
          @input="inputChanged"
          @keydown.enter="search"
        />
        <button
          :disabled="searching || busy || keyword.trim().length < 2 || !policy?.enabled"
          @click="search"
        >
          {{ searching ? '搜索中' : '搜索' }}
        </button>
      </div>
      <div class="access-search-options">
        <button
          class="access-text-button"
          :aria-pressed="picking"
          :disabled="busy"
          @click="picking = !picking"
        >
          {{ picking ? '地图选点已开启' : '开启地图选点' }}
        </button>
        <label title="启用后输入会请求高德地点提示"
          ><input v-model="autocomplete" type="checkbox" :disabled="busy || !policy?.enabled" />
          自动补全</label
        >
      </div>
      <ul v-if="suggestions.length" class="place-suggestions" aria-label="地点搜索建议">
        <li v-for="(item, index) in suggestions" :key="index">
          <button :disabled="busy" @click="choose(item.position, item.name, true)">
            <strong>{{ item.name }}</strong
            ><span>{{ item.address }}</span>
          </button>
        </li>
      </ul>
      <div v-if="origin" class="origin-summary">
        <span class="access-origin-dot"></span
        ><strong :title="origin.name">{{ origin.name }}</strong
        ><button
          class="access-text-button"
          :disabled="busy"
          @click="clearQuery"
          title="清除查询并恢复选点前视角"
        >
          清除
        </button>
      </div>
    </section>
    <section class="access-block access-query-block">
      <button class="access-primary-action" :disabled="!origin || busy" @click="query">
        {{ busy ? '正在获取道路结果…' : '分析驾车可达性' }}<span aria-hidden="true">→</span>
      </button>
      <p v-if="!origin" class="hint">选定起点后，比较附近公共候选站点。</p>
    </section>
    <p v-if="error" class="query-warning" role="alert">{{ error }}</p>
    <p v-if="policy && !policy.enabled" class="query-warning">真实查询未启用，当前仅可读取缓存。</p>
    <section
      v-if="result && fastest"
      class="access-block access-result-summary"
      aria-label="驾车结果摘要"
      aria-live="polite"
    >
      <div class="access-section-heading">
        <span class="access-section-label">结果摘要</span
        ><span class="access-tag"
          >{{ validRoutes.length }}/{{ result.candidates.length }} 已查询</span
        >
      </div>
      <div class="access-summary-metrics">
        <div>
          <span>最快预计驾车</span><strong>{{ minutes(fastest) }}<small>分钟</small></strong>
        </div>
        <div>
          <span>10分钟内可达</span><strong>{{ withinTen }}<small>个站点</small></strong>
        </div>
      </div>
      <p class="access-fastest-name" :title="fastest.name">最快候选 · {{ fastest.name }}</p>
    </section>
    <section v-if="result" class="route-results" aria-label="候选站点列表">
      <div class="access-section-heading">
        <h2>
          候选站点 <small>{{ result.candidates.length }}</small>
        </h2>
        <button class="access-text-button" @click="fitRoutes" :disabled="!result.candidates.length">
          定位路线 ↗
        </button>
      </div>
      <article
        v-for="(station, index) in result.candidates"
        :key="station.id"
        class="route-station"
        :class="{ selected: selectedId === station.id }"
      >
        <button
          class="access-route-select"
          :aria-pressed="selectedId === station.id"
          @click="selectedId = station.id"
        >
          <span class="access-station-number">{{ index + 1 }}</span
          ><span class="access-station-content"
            ><strong class="access-station-name" :title="station.name">{{ station.name }}</strong
            ><span class="access-selected-label" v-if="selectedId === station.id">当前路线</span
            ><span class="route-metrics" v-if="resolved(station)"
              ><b>{{ minutes(station) }}<small> 分钟</small></b
              ><span>{{ distance(station) }} km</span></span
            ><span v-else class="hint">{{
              statuses[station.route?.status] || '暂无道路轨迹'
            }}</span></span
          >
        </button>
        <div v-if="resolved(station)" class="thresholds">
          <span
            v-for="minute in [5, 10, 15]"
            :key="minute"
            :class="{ reachable: station.route.durationSeconds <= minute * 60 }"
            >{{ minute }}分钟
            {{ station.route.durationSeconds <= minute * 60 ? '可达' : '不可达' }}</span
          >
        </div>
        <button
          class="access-text-button access-address-toggle"
          :aria-expanded="expandedId === station.id"
          @click="expandedId = expandedId === station.id ? null : station.id"
        >
          {{ expandedId === station.id ? '收起地址' : '查看地址' }}
          <span aria-hidden="true">{{ expandedId === station.id ? '−' : '+' }}</span>
        </button>
        <p v-if="expandedId === station.id" class="station-address">
          {{ station.address || '暂无地址' }}
        </p>
      </article>
      <div class="access-result-foot">
        <span>缓存 {{ result.cacheHits }} · 新请求 {{ result.apiCalls || 0 }}</span
        ><time v-if="result.queriedAt"
          >{{
            new Date(result.queriedAt).toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
            })
          }}
          更新</time
        >
      </div>
    </section>
    <details class="query-method">
      <summary>数据与方法</summary>
      <p v-if="origin">
        起点：{{ origin.name }} · {{ origin.longitude.toFixed(6) }},
        {{ origin.latitude.toFixed(6) }} · GCJ-02
      </p>
      <p>
        在现有真实POI库中筛选20km直线范围内最近的3个公共候选站点，仅用于候选筛选；道路时间、距离与蓝色轨迹均来自高德驾车结果。旧缓存缺少轨迹时需补查，不绘制直线替代路线。
      </p>
      <p>
        结果按候选驾车时间排序，不保证全库最快。5/10/15分钟为起点到站点的判断，不代表人口、面积覆盖或实时营业状态。与122区县代表点统计独立，不写入其快照。
      </p>
      <p>
        路线缓存有效期7天，地点提示6小时；失败不自动重试。项目不设每日调用次数上限，高德账号配额与计费规则仍然适用。
      </p>
      <p v-if="policy">
        今日已请求：驾车 {{ policy.drivingCallsToday }} 次，地点提示
        {{ policy.placesCallsToday }} 次（UTC日计数，无本地每日上限）。
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
