import { classificationLabels, reviewStatusLabels } from '../config/analysis.js'
export const metricKeys = ['count', 'density', 'coveragePercent']
export const defaultClassification = 'public_candidate'
export function parseAnalysisFilters(query = {}, routeCity = '', cityCodes = []) {
  const read = (key) => {
    if (query[key] == null) return ''
    if (typeof query[key] !== 'string') throw new Error('筛选参数不能重复')
    return query[key]
  }
  const cityCode = routeCity || read('city'),
    districtCode = read('district')
  const requestedClassification = read('classification')
  const classification =
      requestedClassification === 'all' ? '' : requestedClassification || defaultClassification,
    reviewStatus = read('review_status')
  const batch = read('batch'),
    activeMetric = read('metric') || 'count'
  const reviewFlag = read('needs_review')
  if (reviewFlag && reviewFlag !== 'true') throw new Error('待复核线索参数无效')
  const needsReview = reviewFlag === 'true'
  if (cityCode && !cityCodes.includes(cityCode)) throw new Error('请选择湖南省有效市州')
  if (
    districtCode &&
    (!/^43\d{4}$/.test(districtCode) ||
      districtCode.endsWith('00') ||
      !cityCode ||
      !districtCode.startsWith(cityCode.slice(0, 4)))
  )
    throw new Error('区县不属于当前市州')
  if (classification && !Object.hasOwn(classificationLabels, classification))
    throw new Error('POI类别无效')
  if (reviewStatus && !Object.hasOwn(reviewStatusLabels, reviewStatus))
    throw new Error('复核状态无效')
  if (batch && !/^[a-f0-9]{32}$/.test(batch)) throw new Error('数据批次无效')
  if (!metricKeys.includes(activeMetric)) throw new Error('分析指标无效')
  return { cityCode, districtCode, classification, reviewStatus, needsReview, batch, activeMetric }
}
export function analysisFilterQuery(state, routeCity = '') {
  return Object.fromEntries(
    Object.entries({
      city: routeCity ? '' : state.cityCode,
      district: state.districtCode,
      classification:
        state.classification === defaultClassification ? '' : state.classification || 'all',
      review_status: state.reviewStatus,
      needs_review: state.needsReview ? 'true' : '',
      batch: state.batch,
      metric: state.activeMetric === 'count' ? '' : state.activeMetric,
    }).filter(([, value]) => value),
  )
}
export function cityAnalysisRoute(state, cityCode, districtCode = '') {
  return {
    path: `/city/${cityCode}`,
    query: analysisFilterQuery({ ...state, cityCode, districtCode }, cityCode),
  }
}
