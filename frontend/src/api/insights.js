import { http } from './http'
import { classificationLabels, reviewStatusLabels } from '@/config/analysis'

// Real interfaces only: no offline/mock fallback and no provider requests.
export const insightSnapshot = (params, signal) => http.get('/analysis/latest', { params, signal })
export const insightLayer = (layer, params, signal) =>
  http.get(`/analysis/layers/${layer}`, { params, signal })
export const insightRoad = (params, signal) =>
  http.get('/analysis/accessibility/latest', { params, signal })
export async function insightQuality(scope, signal) {
  const classes = scope.classification ? [scope.classification] : Object.keys(classificationLabels)
  const statuses = scope.review_status ? [scope.review_status] : Object.keys(reviewStatusLabels)
  const jobs = classes.flatMap((classification) =>
    statuses.map((review_status) => ({ classification, review_status })),
  )
  const result = Array(jobs.length)
  let cursor = 0
  async function worker() {
    while (cursor < jobs.length && !signal.aborted) {
      const index = cursor++,
        job = jobs[index]
      const data = await http.get('/quality/pois', {
        signal,
        params: { ...scope, ...job, all_records: !scope.needs_review, page_size: 1, page: 1 },
      })
      if (!Number.isInteger(data.total) || data.total < 0)
        throw new Error('治理计数缺失，不能按零处理')
      result[index] = { ...job, count: data.total }
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, jobs.length) }, worker))
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  return {
    rows: result,
    observedAt: new Date().toISOString(),
    filters: { ...scope },
    source: '当前POI治理记录（非空间快照）',
  }
}
