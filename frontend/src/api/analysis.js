import { http } from './http.js'
export const getAnalysisSnapshot = (params, signal) =>
  http.get('/analysis/latest', { params, signal })
export const getAnalysisBoundaries = (parent, signal) =>
  http.get('/analysis/boundaries', { params: { parent }, signal })
export const getAnalysisLayer = (layer, params, signal) =>
  http.get(`/analysis/layers/${layer}`, { params, signal })
export const getQualityPois = (params, signal) => http.get('/quality/pois', { params, signal })
export const getPoiReviewEvents = (stationId, signal) =>
  http.get(`/quality/pois/${stationId}/reviews`, { signal })
