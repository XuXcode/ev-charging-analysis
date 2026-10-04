<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { useAnalysisStore } from '@/stores/analysis'
import AppIcon from './AppIcon.vue'
import { formatNumber } from '@/utils/format'
import { cityAnalysisRoute } from '@/utils/analysis-filters'
const store = useDashboardStore()
const analysis = useAnalysisStore()
const analytical = computed(() => props.sampleMode && !!analysis.snapshot)
const props = defineProps({ sampleMode: Boolean })
const router = useRouter()
const sampleMetric = ref('samples')
const currentMetric = computed({
  get: () =>
    analytical.value
      ? analysis.activeMetric
      : props.sampleMode
        ? sampleMetric.value
        : store.rankingMetric,
  set: (value) => {
    if (analytical.value) analysis.activeMetric = value
    else if (props.sampleMode) sampleMetric.value = value
    else store.rankingMetric = value
  },
})
const rows = computed(() =>
  analytical.value
    ? analysis.cities
        .map((row) => ({ ...store.cities.find((city) => city.code === row.code), ...row }))
        .sort((a, b) => b[currentMetric.value] - a[currentMetric.value])
    : props.sampleMode
      ? (analysis.classification || analysis.reviewStatus || analysis.needsReview || analysis.batch
          ? []
          : store.cities
        )
          .map((city) => ({
            ...city,
            samples:
              store.collectionInfo?.cities.find((row) => row.cityCode === city.code)?.storedCount ??
              null,
          }))
          .sort((a, b) => (b.samples ?? -1) - (a.samples ?? -1))
      : store.ranking,
)
const value = (city) =>
  analytical.value
    ? city[currentMetric.value]
    : props.sampleMode
      ? city.samples
      : city[store.rankingMetric]
const unit = computed(() =>
  analytical.value
    ? analysis.definition?.unit
    : props.sampleMode
      ? currentMetric.value === 'share'
        ? '%'
        : '条'
      : store.activeIndicator?.unit,
)
const options = computed(() =>
  analytical.value
    ? [
        { label: '样本数', value: 'count' },
        { label: '样本密度', value: 'density' },
        { label: '1km覆盖', value: 'coveragePercent' },
      ]
    : props.sampleMode
      ? [
          { label: '样本数量', value: 'samples' },
          { label: '样本占比', value: 'share' },
        ]
      : store.indicatorDefinitions.map((d) => ({
          label: d.key === 'density' ? '密度' : d.label,
          value: d.key,
        })),
)
const format = (city) =>
  props.sampleMode && currentMetric.value === 'share'
    ? Number.isFinite(city.samples) && store.collectionInfo?.storedCount > 0
      ? ((city.samples / store.collectionInfo.storedCount) * 100).toFixed(2) + '%'
      : '—'
    : Number.isFinite(value(city))
      ? formatNumber(
          value(city),
          analytical.value
            ? currentMetric.value === 'density'
              ? 3
              : currentMetric.value === 'coveragePercent'
                ? 2
                : 0
            : props.sampleMode
              ? 0
              : store.activeIndicator?.precision || 0,
        )
      : '—'
function choose(city) {
  if (props.sampleMode) router.push(cityAnalysisRoute(analysis, city.code))
  else store.selectCity(city.code)
}
</script>
<template>
  <section class="panel ranking-panel">
    <div class="panel-heading">
      <div>
        <h2>{{ sampleMode ? '市州样本分布' : '市州指标' }} <small>14市州</small></h2>
        <p>{{ sampleMode ? '高德可检索POI · 悬停定位' : '完整统计接入后显示排名' }}</p>
      </div>
    </div>
    <a-segmented
      v-model:value="currentMetric"
      :options="options"
      block
      aria-label="排名与地图指标"
    />
    <div class="ranking-header">
      <span>市州</span><span>{{ unit }}</span>
    </div>
    <ol class="ranking-list" @mouseleave="store.hoverCity()">
      <li v-for="(city, i) in rows" :key="city.code">
        <button
          class="rank-row"
          :class="{
            selected: store.selectedCodes.includes(city.code),
            hovered: store.highlightedCodes.includes(city.code),
          }"
          :aria-pressed="sampleMode ? undefined : store.selectedCityCode === city.code"
          :aria-label="sampleMode ? `进入${city.name}详情` : `联动${city.name}`"
          @click="choose(city)"
          @mouseenter="store.hoverCity(city.code)"
          @focus="store.hoverCity(city.code)"
          @blur="store.hoverCity()"
        >
          <span class="rank-number" :class="{ top: i < 3 }">{{
            Number.isFinite(value(city)) ? String(i + 1).padStart(2, '0') : '—'
          }}</span>
          <div class="rank-city">
            <span
              >{{ city.shortName || city.name
              }}<small v-if="city.completenessWarning" title="相关区县检索触及上限，样本可能不完整">
                *</small
              ></span
            >
            <div class="rank-track">
              <i
                :style="{
                  width:
                    Number.isFinite(value(city)) && value(rows[0]) > 0
                      ? `${(value(city) / value(rows[0])) * 100}%`
                      : '0%',
                }"
              />
            </div>
          </div>
          <strong>{{ format(city) }}</strong>
        </button>
      </li>
    </ol>
    <div class="panel-note">
      <router-link v-if="store.selectedCity" :to="`/city/${store.selectedCity.code}`"
        >{{ store.selectedCity.shortName }}市州详情 <AppIcon name="arrow" :size="14" /></router-link
      ><span v-else>{{
        sampleMode ? '点击进入市州 · 非官方设施总量' : '点击联动 · 悬停定位'
      }}</span>
    </div>
  </section>
</template>
