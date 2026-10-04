/** Escape API labels before interpolation in ECharts / AMap HTML tooltips. */
export function formatNumber(value, precision = 0) {
  return Number.isFinite(value)
    ? value.toLocaleString('zh-CN', { maximumFractionDigits: precision })
    : '—'
}

export function formatShare(value, total) {
  return Number.isFinite(value) && Number.isFinite(total) && total > 0
    ? ((value / total) * 100).toFixed(1) + '%'
    : '—'
}

export function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char],
  )
}
