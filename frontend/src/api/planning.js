import { http } from './http.js'
export const getPlanningSnapshot = (params, signal) =>
  http.get('/planning/latest', { params, signal })
export const getPlanningLayer = (params, signal) =>
  http.get('/planning/layers/planning', { params, signal })
export const getPlanningPois = (params, signal) =>
  http.get('/planning/pois', { params, signal })