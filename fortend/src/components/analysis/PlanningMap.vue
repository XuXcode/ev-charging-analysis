<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { loadAMap } from '@/utils/amap'
import { escapeHtml } from '@/utils/format'
const props = defineProps({
  existing: { type: Array, default: () => [] },
  candidates: { type: Array, default: () => [] },
  recommended: { type: Array, default: () => [] },
  origins: { type: Array, default: () => [] },
  focusId: { type: String, default: '' },
})
const element = ref(null),
  error = ref('')
let map,
  AMap,
  popup,
  disposed = false,
  markers = []
function render() {
  if (!map) return
  map.remove(markers)
  markers = []
  const selected = new Set(props.recommended.map((r) => r.id))
  const groups = [
    [props.existing, '#6b8279', '原有公共候选站'],
    [props.candidates.filter((r) => !selected.has(r.id)), '#b8994f', '候选设施'],
    [props.recommended, '#146947', '推荐新增候选'],
    [props.origins, '#618fc2', '真实需求观测点'],
  ]
  for (const [rows, color, label] of groups)
    for (const row of rows) {
      const marker = new AMap.Marker({
        position: row.position,
        title: `${label} · ${row.name}`,
        anchor: 'center',
        content: `<span style="display:block;width:12px;height:12px;border:2px solid white;border-radius:50%;background:${color};box-shadow:0 1px 4px #0004"></span>`,
      })
      marker.on('click', () => {
        popup.setContent(
          `<strong>${escapeHtml(row.name)}</strong><p>${label}</p><p>${escapeHtml(row.source || '高德入库POI')} · ${escapeHtml(row.poiId || row.id)}</p><small>设施候选不代表取得建设或用地许可。</small>`,
        )
        popup.open(map, row.position)
      })
      markers.push(marker)
    }
  map.add(markers)
  if (markers.length) map.setFitView(markers, false, [35, 35, 35, 35], 14)
}
onMounted(async () => {
  try {
    AMap = await loadAMap()
    if (disposed) return
    map = new AMap.Map(element.value, {
      center: [112.5, 27.7],
      zoom: 7,
      mapStyle: 'amap://styles/normal',
      resizeEnable: true,
    })
    popup = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -12) })
    render()
  } catch {
    if (!disposed) error.value = '高德地图未加载，请检查地图配置或网络。'
  }
})
watch(() => [props.existing, props.candidates, props.recommended, props.origins], render)
watch(
  () => props.focusId,
  (id) => {
    const row = [...props.recommended, ...props.candidates, ...props.origins].find(
      (item) => item.id === id,
    )
    if (row && map) map.setZoomAndCenter(14, row.position, false, 450)
  },
)
onBeforeUnmount(() => {
  disposed = true
  popup?.close()
  map?.destroy()
})
</script>
<template>
  <div>
    <p v-if="error" role="alert">{{ error }}</p>
    <div ref="element" class="planning-map" aria-label="选址方案真实点位地图" />
    <p class="map-legend">灰绿：原有站点 · 金色：真实候选 · 深绿：推荐候选 · 蓝色：需求观测</p>
  </div>
</template>
<style scoped>
.planning-map {
  height: 410px;
  border-radius: 8px;
  overflow: hidden;
}
.map-legend {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}
</style>
