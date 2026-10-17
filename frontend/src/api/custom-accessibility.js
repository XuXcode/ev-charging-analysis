import { http } from './http'
const base = '/analysis/accessibility/custom'
export const getCustomPolicy = () => http.get(`${base}/policy`)
export const planCustomRoutes = (body) => http.post(`${base}/plan`, body)
export const queryCustomRoutes = (body) => http.post(`${base}/routes`, body, { timeout: 70000 })
export const searchCustomPlaces = (keyword, signal) =>
  http.get(`${base}/places`, { params: { keyword }, signal })
