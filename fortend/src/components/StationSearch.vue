<script setup>
import { computed, ref, watch } from 'vue'
import { Drawer } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useStationSearch } from '@/composables/useStationSearch'
import { cityAnalysisRoute } from '@/utils/analysis-filters'
import { classificationLabels } from '@/config/analysis'
const analysis = useAnalysisStore(),
  router = useRouter(),
  search = useStationSearch()
const open = ref(false),
  text = ref(''),
  currentScope = ref(false)
const scopeLabel = computed(() => classificationLabels[analysis.classification] || '全部类别')
function run(page = 1, immediate = false) {
  return search.search(
    text.value,
    {
      city: currentScope.value ? analysis.cityCode || undefined : undefined,
      adcode: currentScope.value ? analysis.districtCode || undefined : undefined,
      classification: analysis.classification || undefined,
      review_status: analysis.reviewStatus || undefined,
      needs_review: analysis.needsReview || undefined,
      batch: analysis.batch || undefined,
    },
    page,
    immediate,
  )
}
watch([text, currentScope], () => run())
watch(
  () => [
    analysis.classification,
    analysis.reviewStatus,
    analysis.needsReview,
    analysis.batch,
    analysis.cityCode,
    analysis.districtCode,
  ],
  () => {
    if (open.value) run()
    else search.cancel()
  },
)
watch(open, (visible) => {
  if (!visible) search.cancel()
  else if (text.value.trim()) run(1, true)
})
function select(station) {
  analysis.selectedStation = station
  const target = cityAnalysisRoute(analysis, station.cityCode, station.adcode)
  target.query.station = station.poiId
  open.value = false
  router.push(target)
}
</script>
<template>
  <button class="station-search-trigger" @click="open = true">搜索站点</button>
  <Drawer v-model:open="open" title="入库站点搜索" :width="520" :destroy-on-close="false">
    <section class="station-search-panel" aria-label="全库站点搜索">
      <label
        >名称、地址或POI ID<input
          v-model="text"
          type="search"
          maxlength="100"
          placeholder="输入站点名称、地址或POI ID"
          @keydown.enter.prevent="search.items.value[0] && select(search.items.value[0])"
      /></label>
      <label v-if="analysis.cityCode" class="scope-checkbox"
        ><input v-model="currentScope" type="checkbox" />仅当前市州 / 区县</label
      >
      <p>
        搜索口径：{{ scopeLabel }}{{ analysis.needsReview ? ' · 仅待复核线索' : '' }} ·
        沿用当前复核状态与批次。
      </p>
      <p v-if="!text.trim()">输入关键词检索已入库的真实POI；选择结果打开对应区县地图。</p>
      <p v-else-if="search.loading.value" role="status">正在检索…</p>
      <p v-else-if="search.error.value" role="alert">
        {{ search.error.value }} <button @click="run(1, true)">重试</button>
      </p>
      <template v-else>
        <p role="status">{{ search.total.value }}条匹配 · 数据来源：高德开放平台</p>
        <ol>
          <li v-for="station in search.items.value" :key="station.id">
            <button @click="select(station)">
              <strong>{{ station.name }}</strong
              ><span
                >{{ station.city }} / {{ station.district }} ·
                {{ station.address || '地址未提供' }}</span
              ><small
                >{{ station.poiId }} ·
                {{ classificationLabels[station.classification] || '待分类' }}</small
              >
            </button>
          </li>
        </ol>
        <p v-if="!search.total.value">
          当前关键词和筛选没有匹配的入库样本，缺失不代表当地没有设施。
        </p>
        <div v-if="search.total.value > search.pageSize" class="search-pagination">
          <button :disabled="search.page.value <= 1" @click="run(search.page.value - 1, true)">
            上一页</button
          ><span
            >第{{ search.page.value }} /
            {{ Math.ceil(search.total.value / search.pageSize) }}页</span
          ><button
            :disabled="search.page.value * search.pageSize >= search.total.value"
            @click="run(search.page.value + 1, true)"
          >
            下一页
          </button>
        </div>
      </template>
    </section>
  </Drawer>
</template>
<style scoped>
.station-search-trigger,
.station-search-panel button {
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--primary-dark);
  cursor: pointer;
}
.station-search-panel > label {
  display: grid;
  gap: var(--space-2);
  font-weight: 600;
}
input[type='search'] {
  min-height: 40px;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font: inherit;
}
.station-search-panel .scope-checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
  font-weight: 400;
}
p,
small {
  color: var(--text-secondary);
  font-size: var(--type-caption);
  line-height: 1.7;
}
ol {
  padding: 0;
  list-style: none;
  margin: 0;
}
li {
  margin-bottom: var(--space-2);
}
li button {
  width: 100%;
  text-align: left;
  display: grid;
  gap: 6px;
  padding: var(--space-3) !important;
  overflow-wrap: anywhere;
}
li button:hover {
  background: var(--primary-soft);
}
li span {
  color: var(--text-secondary);
  font-size: var(--type-caption);
}
.search-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
</style>
