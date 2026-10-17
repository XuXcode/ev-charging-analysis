<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import { useLayoutStore } from '@/stores/layout'
import { demoMode } from '@/api/demo-fallback'
import { topics } from '@/config/topics'
import { cityMapConfig } from '@/config/maps'
import { analysisFilterQuery } from '@/utils/analysis-filters'
import AppIcon from '@/components/AppIcon.vue'
import AnalysisFilter from '@/components/analysis/AnalysisFilter.vue'
import StationSearch from '@/components/StationSearch.vue'
import ViewState from '@/components/ViewState.vue'

defineProps({
  scene: { type: String, default: 'overview' },
  panelEyebrow: { type: String, default: '' },
  panelTitle: { type: String, default: '' },
  panelSubtitle: { type: String, default: '' },
})

const store = useDashboardStore()
const analysis = useAnalysisStore()
const layout = useLayoutStore()
const route = useRoute()

const provinceRoute = computed(() => ({
  path: '/',
  query: analysisFilterQuery({ ...analysis, cityCode: '', districtCode: '' }),
}))
const navItems = computed(() => [
  {
    key: 'overview',
    title: '全省总览',
    subtitle: '省级格局与市州样本',
    icon: 'map',
    to: provinceRoute.value,
    active: route.name === 'overview' || route.name === 'city',
  },
  ...topics.map((topic) => ({
    key: topic.slug,
    title: topic.title,
    subtitle: topic.description,
    icon: topic.icon,
    to: { path: `/analysis/${topic.slug}`, query: analysisFilterQuery(analysis) },
    active: route.params.topic === topic.slug,
  })),
])

const breadcrumbCity = computed(() => cityMapConfig[analysis.cityCode])
const breadcrumbDistrict = computed(() =>
  analysis.districtCatalog.find((row) => row.code === analysis.districtCode),
)
const breadcrumbStation = computed(() =>
  typeof route.query.station === 'string'
    ? analysis.selectedStation?.poiId === route.query.station
      ? analysis.selectedStation.name
      : `站点 ${route.query.station}`
    : '',
)
const pageLabel = computed(() =>
  route.name === 'city'
    ? '市州详情'
    : route.name === 'analysis'
      ? topics.find((t) => t.slug === route.params.topic)?.shortTitle || '专题分析'
      : '全省总览',
)

const isDemo = computed(() => demoMode.value || store.sourceInfo?.simulated === true)
const monitorRoot = ref(null)
const filterStrip = ref(null)
let filterObserver
function exitOnEscape(event) {
  if (event.key === 'Escape' && layout.pureMap && !event.defaultPrevented) layout.exitPureMap()
}
watch(
  () => route.fullPath,
  () => layout.exitPureMap(),
)
onMounted(() => {
  window.addEventListener('keydown', exitOnEscape)
  filterObserver = new ResizeObserver(() => {
    const height = filterStrip.value?.getBoundingClientRect().height
    if (height) monitorRoot.value?.style.setProperty('--monitor-filter-measured', `${height}px`)
  })
  if (filterStrip.value) filterObserver.observe(filterStrip.value)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', exitOnEscape)
  filterObserver?.disconnect()
})
</script>
<template>
  <main
    ref="monitorRoot"
    class="app-monitor"
    :data-scene="scene"
    :data-left="String(layout.leftCollapsed)"
    :data-right="String(layout.rightCollapsed)"
    :data-filter="String(layout.filterOpen)"
    :data-pure="String(layout.pureMap)"
    id="main-content"
    tabindex="-1"
  >
    <div class="hud-map-safearea" aria-hidden="true" />
    <div id="gis-map-stage" class="map-stage"><slot name="map" /></div>
    <header class="hud-topbar glass-surface">
      <router-link :to="provinceRoute" class="hud-brand">
        <span class="hud-brand__mark"><AppIcon name="bolt" :size="22" /></span>
        <span><strong>湖南充电 · 空间分析</strong><small>湖南省新能源汽车充电设施</small></span>
      </router-link>
      <div class="hud-topbar__mid">
        <span class="hud-page-label">{{ pageLabel }}</span
        ><slot name="topbar-mid" />
      </div>
      <div class="hud-topbar__right">
        <span v-if="isDemo" class="hud-status is-demo"><i class="hud-dot" />离线快照</span>
        <div class="hud-global-search"><StationSearch /></div>
        <button
          class="hud-icobtn hud-global-filter-toggle"
          :aria-pressed="layout.filterOpen"
          :aria-label="layout.filterOpen ? '收起筛选条' : '展开筛选条'"
          title="筛选条件"
          @click="layout.toggleFilter()"
        >
          <AppIcon name="layers" :size="18" />
        </button>
        <button
          class="hud-focus-button"
          :aria-pressed="layout.pureMap"
          :aria-label="layout.pureMap ? '退出纯地图模式' : '进入纯地图模式'"
          @click="layout.togglePureMap()"
        >
          <AppIcon :name="layout.pureMap ? 'back' : 'expand'" :size="17" /><span>{{
            layout.pureMap ? '返回分析' : '纯地图'
          }}</span>
        </button>
      </div>
    </header>
    <section
      id="gis-map-tools"
      ref="filterStrip"
      class="hud-filterstrip glass-surface"
      :inert="layout.pureMap || undefined"
      aria-label="分析筛选"
    >
      <nav
        class="hud-breadcrumb"
        aria-label="当前位置"
        :title="
          ['湖南省', breadcrumbCity?.name, breadcrumbDistrict?.name, breadcrumbStation]
            .filter(Boolean)
            .join(' / ')
        "
      >
        <router-link :to="provinceRoute">湖南省</router-link><span>/</span
        ><strong>{{ pageLabel }}</strong>
        <template v-if="breadcrumbCity"
          ><span>/</span
          ><router-link
            :to="{
              path: `/city/${breadcrumbCity.code}`,
              query: analysisFilterQuery({ ...analysis, districtCode: '' }, breadcrumbCity.code),
            }"
            >{{ breadcrumbCity.shortName || breadcrumbCity.name }}</router-link
          ></template
        >
        <template v-if="breadcrumbDistrict && breadcrumbCity"
          ><span>/</span><strong>{{ breadcrumbDistrict.name }}</strong></template
        >
        <template v-if="breadcrumbStation"
          ><span>/</span><strong>{{ breadcrumbStation }}</strong></template
        >
      </nav>
      <div class="hud-region-filter">
        <button
          class="hud-region-trigger"
          :aria-expanded="layout.filterOpen"
          @click="layout.toggleFilter()"
        >
          区域筛选 <AppIcon name="layers" :size="14" />
        </button>
        <div v-if="layout.filterOpen" class="hud-filter-popover"><AnalysisFilter /></div>
      </div>
    </section>
    <aside
      class="hud-rail hud-rail--left glass-surface"
      :class="{ 'is-collapsed': layout.leftCollapsed }"
      :inert="layout.pureMap || undefined"
    >
      <div class="hud-nav-heading">
        <span>分析工作台</span
        ><button
          class="hud-icobtn"
          :aria-label="layout.leftCollapsed ? '展开左侧导航' : '收起左侧导航'"
          @click="layout.toggleLeft()"
        >
          <AppIcon :name="layout.leftCollapsed ? 'arrow' : 'back'" :size="17" />
        </button>
      </div>
      <nav class="hud-nav" aria-label="主导航">
        <router-link
          v-for="(item, index) in navItems"
          :key="item.key"
          :to="item.to"
          :title="item.title"
          class="hud-nav__item"
          :class="{ 'is-active': item.active }"
          :aria-current="item.active ? 'page' : undefined"
          ><span class="hud-nav__icon"><AppIcon :name="item.icon" :size="20" /></span
          ><span class="hud-nav__text"
            ><strong>{{ item.title }}</strong
            ><small>{{ item.subtitle }}</small></span
          ><span class="hud-nav__index">0{{ index + 1 }}</span></router-link
        >
      </nav>
    </aside>
    <section
      v-if="$slots.workspace"
      class="hud-workspace"
      :inert="layout.pureMap || undefined"
      aria-label="专题分析工作区"
    >
      <slot name="workspace" />
    </section>
    <div
      v-if="$slots['map-summary']"
      class="hud-map-summary glass-surface"
      :inert="layout.pureMap || undefined"
    >
      <slot name="map-summary" />
    </div>
    <aside
      class="hud-rail hud-rail--right glass-surface"
      :class="{ 'is-collapsed': layout.rightCollapsed }"
      :inert="layout.pureMap || undefined"
      aria-label="分析面板"
    >
      <header class="hud-panel__head">
        <div>
          <span class="hud-eyebrow">{{ panelEyebrow || pageLabel }}</span>
          <h1>{{ panelTitle }}</h1>
          <p v-if="panelSubtitle">{{ panelSubtitle }}</p>
        </div>
        <button
          class="hud-icobtn"
          :aria-label="layout.rightCollapsed ? '展开右侧面板' : '收起右侧面板'"
          @click="layout.toggleRight()"
        >
          <AppIcon :name="layout.rightCollapsed ? 'back' : 'arrow'" :size="17" />
        </button>
      </header>
      <div v-if="$slots['panel-actions']" class="hud-panel__tools">
        <slot name="panel-actions" />
      </div>
      <div v-if="$slots['panel-controls']" class="hud-panel__controls">
        <slot name="panel-controls" />
      </div>
      <div class="hud-panel__body">
        <ViewState
          v-if="analysis.filterError"
          kind="error"
          title="筛选参数无效"
          :description="analysis.filterError"
          @retry="analysis.resetFilters()"
        /><slot />
      </div>
      <span class="hud-rail__stub" aria-hidden="true">分析面板</span>
    </aside>

    <div v-if="layout.pureMap" class="hud-pure-hint glass-surface">
      纯地图模式 <kbd>Esc</kbd> 返回分析
    </div>
  </main>
</template>
