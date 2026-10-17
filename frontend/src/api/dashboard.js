import { http } from './http.js'
import { withDemoFallback } from './demo-fallback.js'
import { demoDashboard, demoCollectionSummary } from './demo/offline-snapshot.js'
/** FastAPI contract: GET /dashboard -> { cities, stations, metrics, trend, sourceInfo, regions }. */
export async function getDashboard() {
  return withDemoFallback(() => http.get('/dashboard'), demoDashboard, '总览指标')
}
/** Reserved district adapter. No boundary or statistics are fabricated. */
export async function getCityDistricts(cityCode) {
  return http.get(`/cities/${cityCode}/districts`)
}

export const getAMapStatus = () => http.get('/amap/status')
export const getAMapStations = (city, page = 1) =>
  http.get('/amap/stations', { params: { city, page, page_size: 25 } })

// The map reads collected database records; it never falls back to mock stations.
export const getStoredStations = (
  city,
  page = 1,
  {
    bbox,
    adcode,
    classification,
    review_status,
    needs_review,
    batch,
    signal,
    keyword,
    pageSize = 200,
  } = {},
) =>
  http.get('/stations', {
    params: {
      city: city || undefined,
      bbox,
      adcode,
      classification,
      review_status,
      needs_review,
      batch,
      keyword,
      page,
      page_size: pageSize,
      real_only: true,
    },
    signal,
  })
export const getCollectionSummary = () =>
  withDemoFallback(() => http.get('/collection/summary'), demoCollectionSummary, '采集批次汇总')
