import { cityMapConfig, hunan } from '@/config/maps'

/**
 * Values replayed from artifacts that ship with this repository. Nothing here is invented:
 * every figure is copied from one of the three recorded sources below, and any field no
 * artifact records stays null so the UI keeps rendering "—" instead of a made-up number.
 *
 *  - docs/exports/city-poi-samples.csv  → per-city POI sample counts, snapshot f4b14b22…,
 *    algorithm sample-spatial-v1.2, filter {classification: public_candidate}
 *  - docs/reports/GEOMETRY_V12_AUDIT.json → province area / density / 1km coverage for v1.2
 *  - public/data-quality/poi-audit.json → stored (deduplicated) POI counts per city, run ids
 */
const sampleCounts = {
  430100: 3151,
  431000: 889,
  430400: 770,
  431100: 793,
  430600: 766,
  430200: 743,
  430500: 692,
  430700: 666,
  431300: 640,
  430900: 627,
  431200: 596,
  430300: 525,
  430800: 462,
  433100: 400,
}
const storedCounts = {
  430100: 3399,
  430200: 808,
  430300: 571,
  430400: 815,
  430500: 746,
  430600: 850,
  430700: 717,
  430800: 489,
  430900: 660,
  431000: 971,
  431100: 823,
  431200: 628,
  431300: 687,
  433100: 437,
}
// Cities whose recorded export carries the "检索触及上限，样本可能不完整" completeness hint.
const cappedCityCodes = new Set([
  '430100',
  '431000',
  '430600',
  '430200',
  '430700',
  '431300',
  '430900',
  '430800',
])

const snapshotIdentity = {
  snapshotId: 'f4b14b22c8884a58bb4e96e2dd3688f7',
  runId: '77751da1e930432394ebe8325068c3b6',
  supplementRunId: 'f8a52ae0e1ea44528ffac48b4ab073d6',
  algorithmName: 'POI空间分布与1km直线缓冲并集裁剪',
  algorithmVersion: 'sample-spatial-v1.2',
  sourceUpdatedAt: '2026-10-04T02:49:05Z',
  computedAt: '2026-10-04T12:13:40Z',
  frozenInputHash: '33aeeea79863ed9b1320a26531f65fb1376e2ad3e9633f008908ab00ef34d7f9',
  boundaryHash: 'a010692a27bf9fa1a6ba53067b78040d0e6b734929175bf35abc4e54834a9f48',
  // Recorded parameter block from the export's "算法参数与依赖版本" column.
  parameters: {
    radiusM: 1000,
    gridStepM: 5000,
    filters: { classification: 'public_candidate' },
    sourceHash: '3e451e78f63d1f87bdfd85459b0757c36369bfe4139744e015f2a4b9d450fc43',
    bufferModel: 'ellipsoid-scale-ring-on-GCJ-chart',
    coordinateModel: 'GCJ02-chart-LAEA-approximate',
    sampleScope: 'all_retained_pois',
    countAssignment: 'source_adcode',
    displayToleranceM: 25,
  },
}

const provinceMetrics = {
  count: 11720,
  areaKm2: 211959.2320145572,
  density: 0.055293651937723,
  coveredAreaKm2: 13542.677154727788,
  coveragePercent: 6.389283932580812,
  uncoveredAreaKm2: 198416.55485982643,
}

const SOURCE_NOTICE =
  '离线只读核验快照；名称与原始类别仅提供复核线索，不判定真实营业状态或车辆类型。重叠线索不能相加推算无效总量，所有样本均保留。'
const COORDINATE_NOTICE = '供应方文档与来源链路，非逐点实地配准'
const LIMITATION_NOTE =
  '按明确分类/复核/批次条件选择保留POI，不删除原始记录；样本覆盖不代表公共营业设施覆盖。检索上限与几何版本影响结论。'

const cityRows = () =>
  Object.keys(sampleCounts).map((code) => {
    const meta = cityMapConfig[code] || {}
    const count = sampleCounts[code]
    return {
      code,
      cityCode: code,
      name: meta.name || code,
      shortName: meta.shortName || meta.name || code,
      level: 'city',
      count,
      sharePercent: (count / provinceMetrics.count) * 100,
      // No offline artifact records per-city area, density or 1km coverage for v1.2,
      // so these stay null rather than being derived from an unrelated snapshot.
      areaKm2: null,
      density: null,
      coveragePercent: null,
      coveredAreaKm2: null,
      uncoveredAreaKm2: null,
      reviewCount: null,
      qualityStatus: null,
      completenessWarning: cappedCityCodes.has(code),
    }
  })

export function demoDashboard() {
  return {
    cities: Object.keys(storedCounts).map((code) => {
      const meta = cityMapConfig[code] || {}
      return {
        code,
        adcode: code,
        name: meta.name || code,
        shortName: meta.shortName || meta.name || code,
        center: meta.center || null,
        level: 'city',
        region: null,
        // Statistics (充电站/桩/密度) come from verified StatisticSnapshot only. Nothing
        // offline provides them here, so they stay null exactly as the API contract requires
        // instead of reusing the POI sample counts as a stand-in.
        stations: null,
        piles: null,
        density: null,
        areaKm2: null,
        fastRate: null,
        growth: null,
        yoy: null,
        qoq: null,
        sparkline: [],
        completenessWarning: cappedCityCodes.has(code),
      }
    }),
    stations: [],
    metrics: [],
    trend: [],
    regions: [],
    indicatorDefinitions: [
      {
        key: 'stations',
        label: '充电站',
        unit: '座',
        precision: 0,
        description: '统计期末充电站存量；离线快照未提供。',
      },
      {
        key: 'piles',
        label: '公共充电桩',
        unit: '个',
        precision: 0,
        description: '统计期末对外开放的充电桩存量；离线快照未提供。',
      },
      {
        key: 'density',
        label: '设施密度',
        unit: '座/100km²',
        precision: 2,
        description: '充电站存量 ÷ 已核验统计面积 × 100；离线快照未提供。',
      },
    ],
    groupDefinitions: [],
    reservedCharts: [],
    analysisGroups: {},
    cityTrends: {},
    stationPage: null,
    sourceInfo: {
      simulated: true,
      label: '仓库内离线快照（非实时接口）',
      boundary: 'DataV.GeoAtlas 湖南省行政边界（GCJ-02，14市州）',
      period: '记录于 2026-10-04',
      updatedAt: snapshotIdentity.sourceUpdatedAt,
      note: '演示数据：后端接口不可用时回放仓库内离线产物，接口恢复后自动失效。',
    },
  }
}

export function demoCollectionSummary() {
  return {
    source: '仓库内离线快照',
    coordinateSystem: 'GCJ-02',
    simulated: true,
    storedCount: 12601,
    updatedAt: snapshotIdentity.sourceUpdatedAt,
    cities: Object.keys(storedCounts).map((code) => ({
      cityCode: code,
      cityName: cityMapConfig[code]?.name || code,
      storedCount: storedCounts[code],
    })),
    latestRun: {
      id: snapshotIdentity.runId,
      status: null,
      startedAt: null,
      updatedAt: null,
      finishedAt: null,
      lastError: null,
      manifest: null,
      totals: { rawCount: null },
      cities: Object.keys(storedCounts).map((code) => ({
        cityCode: code,
        cityName: cityMapConfig[code]?.name || code,
        storedCount: storedCounts[code],
      })),
      discoveredDistricts: null,
      finishedDistricts: null,
      cappedDistricts: null,
      notice: SOURCE_NOTICE,
    },
    latestSupplement: null,
    notice: SOURCE_NOTICE,
  }
}

// Only the default filter has a recorded offline result. Any other classification / review
// status / batch combination returns null so the caller keeps its real error state instead of
// showing a snapshot computed under a different scope.
export function demoAnalysisSnapshot(params = {}) {
  const scoped =
    (params.classification || 'public_candidate') !== 'public_candidate' ||
    params.review_status ||
    params.needs_review ||
    params.batch
  if (scoped) return null
  return {
    snapshotId: snapshotIdentity.snapshotId,
    computedAt: snapshotIdentity.computedAt,
    stale: false,
    metadata: {
      sourceUpdatedAt: snapshotIdentity.sourceUpdatedAt,
      runId: snapshotIdentity.runId,
      qualityRunIds: [snapshotIdentity.runId, snapshotIdentity.supplementRunId],
      datasetQualityRunIds: [snapshotIdentity.runId, snapshotIdentity.supplementRunId],
      algorithmName: snapshotIdentity.algorithmName,
      algorithmVersion: snapshotIdentity.algorithmVersion,
      stationCount: provinceMetrics.count,
      boundaryHash: snapshotIdentity.boundaryHash,
      frozenInputHash: snapshotIdentity.frozenInputHash,
      coordinateNotice: COORDINATE_NOTICE,
      notice: LIMITATION_NOTE,
      needsReview: null,
      filters: { classification: 'public_candidate' },
      parameters: snapshotIdentity.parameters,
      grid: { gridStepM: 5000, hotspotMethod: '有样本网格密度P95描述性阈值，不是统计显著性检验' },
    },
    province: {
      code: '430000',
      name: '湖南省',
      shortName: '湖南',
      level: 'province',
      ...provinceMetrics,
      sharePercent: 100,
      reviewCount: null,
      qualityStatus: null,
    },
    cities: cityRows(),
    // No offline artifact carries the v1.2 district table, so the district scope stays empty
    // instead of mixing in another snapshot's numbers.
    districts: [],
    indicatorDefinitions: [
      {
        key: 'count',
        label: 'POI样本数量',
        unit: '条',
        precision: 0,
        formula: '当前筛选条件下保留的高德可检索POI样本数；不代表官方设施总量。',
      },
      {
        key: 'density',
        label: 'POI样本密度',
        unit: '条/km²',
        precision: 3,
        formula: '样本数量 ÷ 行政边界模型面积；离线快照仅记录全省值，市州值未记录。',
      },
      {
        key: 'coveragePercent',
        label: '1km样本覆盖率',
        unit: '%',
        precision: 2,
        formula: '站点1km缓冲合并后与行政区求交的面积比例；米制近似，非道路或人口覆盖。',
      },
    ],
  }
}

export function demoBoundaries(parent) {
  // The bundled GeoJSON is the real 14-city boundary of Hunan, so it can serve parent=430000.
  // County boundaries are not shipped with the repository; return null to keep the real error.
  return String(parent) === '430000' ? hunan : null
}
