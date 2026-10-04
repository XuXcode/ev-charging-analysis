<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { topics } from '@/mock/topics'
import AppIcon from '@/components/AppIcon.vue'
import AnalysisFilter from '@/components/analysis/AnalysisFilter.vue'
import ViewState from '@/components/ViewState.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useAnalysisContext } from '@/composables/useAnalysisContext'
import DataSourceInfo from '@/components/DataSourceInfo.vue'
import Loading from '@/components/Loading.vue'
import StationSearch from '@/components/StationSearch.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ExportNotice from '@/components/ExportNotice.vue'
import { token } from '@/utils/chart-theme'
import { cityMapConfig } from '@/config/maps'
import { analysisFilterQuery } from '@/utils/analysis-filters'
const store = useDashboardStore(),
  route = useRoute()
const analysis = useAnalysisStore()
const breadcrumbCity = computed(() => cityMapConfig[analysis.cityCode])
const breadcrumbDistrict = computed(() =>
  analysis.districtCatalog.find((row) => row.code === analysis.districtCode),
)
const provinceRoute = computed(() => ({
  path: '/',
  query: analysisFilterQuery({ ...analysis, cityCode: '', districtCode: '' }),
}))
const breadcrumbStation = computed(() =>
  typeof route.query.station === 'string'
    ? analysis.selectedStation?.poiId === route.query.station
      ? analysis.selectedStation.name
      : `站点 ${route.query.station}`
    : '',
)
useAnalysisContext()
onMounted(() => {
  store.load()
  store.loadCollectionInfo()
})
</script>
<template>
  <a-config-provider
    :theme="{
      token: {
        colorPrimary: token('primary'),
        borderRadius: 6,
        fontFamily: 'Inter, Microsoft YaHei, sans-serif',
        colorText: token('text'),
      },
    }"
    ><div class="app-shell">
      <a href="#main-content" class="skip-link">跳转到主要内容</a>
      <header class="app-header">
        <router-link :to="provinceRoute" class="brand"
          ><span class="brand-symbol"><AppIcon name="bolt" :size="26" /></span>
          <div>
            <strong>湖南省新能源汽车充电基础设施</strong>
            <small>空间分析与可视化平台</small>
          </div></router-link
        >
        <div class="header-status">
          <span class="status-dot" />{{
            store.sourceInfo
              ? store.sourceInfo.simulated
                ? '模拟数据'
                : '真实接口模式'
              : '连接数据服务'
          }}<span class="header-divider" /><span>{{
            store.sourceInfo?.period || '数据加载中'
          }}</span>
        </div>
      </header>
      <nav class="main-nav" aria-label="主导航">
        <router-link
          :to="provinceRoute"
          :class="{ active: route.name === 'overview' || route.name === 'city' }"
          ><AppIcon name="map" :size="17" />全省总览</router-link
        ><router-link
          v-for="topic in topics"
          :key="topic.slug"
          :to="{ path: `/analysis/${topic.slug}`, query: analysisFilterQuery(analysis) }"
          :class="{ active: route.params.topic === topic.slug }"
          ><AppIcon :name="topic.icon" :size="17" />{{ topic.shortTitle }}</router-link
        >
      </nav>
      <main id="main-content" tabindex="-1">
        <Loading v-if="store.loading && !store.loaded" /><EmptyState
          v-else-if="store.error"
          title="数据载入失败"
          :description="store.error"
          ><a-button type="primary" @click="store.load">重新加载</a-button></EmptyState
        ><template v-else-if="store.loaded"
          ><div class="page-toolbar">
            <div class="breadcrumb">
              <router-link :to="provinceRoute">湖南省</router-link><span>/</span
              ><strong>{{
                route.name === 'city'
                  ? '市州详情'
                  : route.name === 'analysis'
                    ? '专题分析'
                    : '全省总览'
              }}</strong>
              <template v-if="breadcrumbCity"
                ><span>/</span
                ><router-link
                  :to="{
                    path: `/city/${breadcrumbCity.code}`,
                    query: analysisFilterQuery(
                      { ...analysis, districtCode: '' },
                      breadcrumbCity.code,
                    ),
                  }"
                  >{{ breadcrumbCity.name }}</router-link
                ></template
              >
              <template v-if="breadcrumbDistrict"
                ><span>/</span
                ><router-link
                  :to="{
                    path: `/city/${breadcrumbCity.code}`,
                    query: analysisFilterQuery(analysis, breadcrumbCity.code),
                  }"
                  >{{ breadcrumbDistrict.name }}</router-link
                ></template
              >
              <template v-if="breadcrumbStation"
                ><span>/</span><strong>{{ breadcrumbStation }}</strong></template
              >
            </div>
            <div class="toolbar-right">
              <StationSearch />
              <span>POI样本口径 · 非官方设施统计</span>
            </div>
          </div>
          <AnalysisFilter />
          <ViewState
            v-if="analysis.filterError"
            kind="error"
            title="筛选参数无效"
            :description="analysis.filterError"
            @retry="analysis.resetFilters()"
          />
          <template v-else>
            <ViewState
              v-if="!analysis.loading && analysis.snapshot?.province.count === 0"
              kind="empty"
              compact
              title="当前筛选无POI样本"
              description="对应真实快照的样本数为0；这不表示湖南省没有充电设施。可调整类别或复核状态，或恢复默认范围。"
            />
            <ErrorBoundary><router-view /></ErrorBoundary>
          </template>
        </template>
      </main>
      <DataSourceInfo /><ExportNotice /></div
  ></a-config-provider>
</template>
