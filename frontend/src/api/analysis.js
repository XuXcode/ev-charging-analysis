import { http } from './http.js'
import { withDemoFallback } from './demo-fallback.js'
import { demoAnalysisSnapshot, demoBoundaries } from './demo/offline-snapshot.js'
export const getAnalysisSnapshot = (params, signal) =>
  withDemoFallback(
    () => http.get('/analysis/latest', { params, signal }),
    () => demoAnalysisSnapshot(params),
    '分析快照',
  )
export const getAnalysisBoundaries = (parent, signal) =>
  withDemoFallback(
    () => http.get('/analysis/boundaries', { params: { parent }, signal }),
    () => demoBoundaries(parent),
    '行政边界',
  )
export const getAnalysisLayer = (layer, params, signal) =>
  http.get(`/analysis/layers/${layer}`, { params, signal })
export const getQualityPois = (params, signal) => http.get('/quality/pois', { params, signal })
export const getPoiReviewEvents = (stationId, signal) =>
  http.get(`/quality/pois/${stationId}/reviews`, { signal })
