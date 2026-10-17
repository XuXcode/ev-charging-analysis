// The renderer fills the viewport; fit real geometry to the space between floating tools.
// Retain only the aspect per element so resizing does not traverse a large grid again.
const geometryAspects = new WeakMap()
function geometryAspect(geojson) {
  let west = Infinity,
    east = -Infinity,
    south = Infinity,
    north = -Infinity
  function visit(coordinates) {
    if (!Array.isArray(coordinates)) return
    if (typeof coordinates[0] === 'number' && typeof coordinates[1] === 'number') {
      const [x, y] = coordinates
      if (!Number.isFinite(x) || !Number.isFinite(y)) return
      west = Math.min(west, x)
      east = Math.max(east, x)
      south = Math.min(south, y)
      north = Math.max(north, y)
    } else coordinates.forEach(visit)
  }
  for (const feature of geojson?.features || []) visit(feature.geometry?.coordinates)
  return east > west && north > south ? ((east - west) / (north - south)) * 0.88 : 0.8
}
export function mapViewport(element, geometry) {
  if (element && geometry) geometryAspects.set(element, geometryAspect(geometry))
  if (!element?.closest('.map-stage')) return {}
  const safe = element.closest('.app-monitor')?.querySelector('.hud-map-safearea')
  if (!safe) return {}
  const bounds = safe.getBoundingClientRect()
  const canvas = element.getBoundingClientRect()
  if (bounds.width <= 0 || bounds.height <= 0) return {}
  const aspect = geometryAspects.get(element) || 0.8
  const size = Math.min(bounds.width * Math.max(1, 1 / aspect), bounds.height * Math.max(1, aspect))
  return {
    layoutCenter: [bounds.x - canvas.x + bounds.width / 2, bounds.y - canvas.y + bounds.height / 2],
    layoutSize: size * 0.98,
  }
}
export function observeMapViewport(observer, element) {
  const safe = element?.closest('.app-monitor')?.querySelector('.hud-map-safearea')
  if (safe && element.closest('.map-stage')) observer.observe(safe)
}

export function mapInsets(element) {
  if (!element?.closest('.map-stage')) return [45, 55, 45, 55]
  const safe = element.closest('.app-monitor')?.querySelector('.hud-map-safearea')
  if (!safe) return [45, 55, 45, 55]
  const r = safe.getBoundingClientRect(),
    c = element.getBoundingClientRect()
  return [
    Math.max(20, r.top - c.top),
    Math.max(20, c.right - r.right),
    Math.max(20, c.bottom - r.bottom),
    Math.max(20, r.left - c.left),
  ]
}
export function mapLegend(element) {
  const padding = mapInsets(element)
  return element?.closest('.map-stage') ? { left: padding[3] + 12, bottom: 42 } : {}
}

export function resizeMapViewport(chart, element) {
  if (!chart || chart.isDisposed() || !element?.clientWidth || !element.clientHeight) return
  chart.resize()
  const viewport = mapViewport(element)
  if (viewport.layoutSize && chart.getOption()?.series?.length) {
    // Merge only geometry layout; keep data, zoom, selection and the existing renderer.
    chart.setOption({ series: [viewport], visualMap: mapLegend(element) }, { lazyUpdate: true })
  }
}
