import outline from '@/assets/hunan-outline.json'
import { MAP_COLORS } from '@/config/maps'

const MIN_CELLS = 1500
const PADDING = 320
const MAX_PIXELS = 12_000_000

// Interaction-only bitmap cache. ECharts retains every feature and owns the sole camera.
// Geometry is never simplified, recoloured, aggregated, or used to recompute statistics.
export function createGridDragPreview(chart, element) {
  let scene = null
  let paths = []
  let cursor = 0
  let idle = 0
  let active = null
  let disposed = false
  const supported = typeof Path2D !== 'undefined' && typeof DOMMatrix !== 'undefined'

  function polygonPath(geometry) {
    const path = new Path2D()
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates
    for (const polygon of polygons)
      for (const ring of polygon) {
        ring.forEach(([x, y], i) => (i ? path.lineTo(x, y) : path.moveTo(x, y)))
        path.closePath()
      }
    return path
  }
  function linePath(lines) {
    const path = new Path2D()
    for (const line of lines)
      line.forEach(([x, y], i) => (i ? path.lineTo(x, y) : path.moveTo(x, y)))
    return path
  }
  function prepare(deadline) {
    idle = 0
    if (!scene || disposed) return
    const start = performance.now()
    while (cursor < scene.cells.length) {
      const cell = scene.cells[cursor++]
      paths.push({ path: polygonPath(cell.geometry), fill: cell.fill })
      if (deadline && (performance.now() - start > 6 || deadline.timeRemaining() < 1)) break
    }
    if (cursor < scene.cells.length && deadline) schedule()
  }
  function schedule() {
    if (typeof requestIdleCallback === 'function') idle = requestIdleCallback(prepare)
  }
  function cancelIdle() {
    if (idle) cancelIdleCallback(idle)
    idle = 0
  }
  function pan(dx, dy) {
    if ((!dx && !dy) || chart.isDisposed()) return
    chart.dispatchAction({ type: 'geoRoam', componentType: 'geo', geoIndex: 0, dx, dy })
    // Paint the final real camera before removing the preview: no intermediate jump.
    chart.getZr().refreshImmediately()
  }
  function begin() {
    if (!supported || !scene || scene.cells.length < MIN_CELLS || disposed) return null
    const source = Array.from(element.querySelectorAll('canvas[data-zr-dom-id]')).find((canvas) =>
      /^zr_0(?:\.0)?$/.test(canvas.getAttribute('data-zr-dom-id')),
    )
    if (!source?.parentElement || !element.clientWidth || !element.clientHeight) return null
    cancelIdle()
    prepare()
    const width = chart.getWidth(),
      height = chart.getHeight()
    const ratio = Math.min(
      chart.getZr().painter.dpr || 1,
      2,
      Math.sqrt(MAX_PIXELS / ((width + 2 * PADDING) * (height + 2 * PADDING))),
    )
    const bitmap = document.createElement('canvas')
    bitmap.className = 'grid-drag-preview'
    bitmap.setAttribute('aria-hidden', 'true')
    bitmap.width = Math.ceil((width + 2 * PADDING) * ratio)
    bitmap.height = Math.ceil((height + 2 * PADDING) * ratio)
    Object.assign(bitmap.style, {
      position: 'absolute',
      left: `-${PADDING}px`,
      top: `-${PADDING}px`,
      width: `${width + 2 * PADDING}px`,
      height: `${height + 2 * PADDING}px`,
      pointerEvents: 'none',
      willChange: 'transform',
    })
    const ctx = bitmap.getContext('2d')
    if (!ctx) return null
    const boundary = linePath(scene.boundaries)
    const exterior = scene.provinceOutline ? linePath(outline.rings) : null
    let dx = 0,
      dy = 0,
      closed = false
    const visibility = source.style.visibility
    function repaint() {
      const origin = chart.convertToPixel({ geoIndex: 0 }, [110, 26])
      const east = chart.convertToPixel({ geoIndex: 0 }, [111, 26])
      const north = chart.convertToPixel({ geoIndex: 0 }, [110, 27])
      if (![origin, east, north].every((p) => p?.every(Number.isFinite))) return false
      const a = east[0] - origin[0],
        b = east[1] - origin[1],
        c = north[0] - origin[0],
        d = north[1] - origin[1]
      const matrix = new DOMMatrix([
        a,
        b,
        c,
        d,
        origin[0] - 110 * a - 26 * c + PADDING,
        origin[1] - 110 * b - 26 * d + PADDING,
      ])
      const project = (path) => {
        const screen = new Path2D()
        screen.addPath(path, matrix)
        return screen
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
      ctx.clearRect(0, 0, bitmap.width / ratio, bitmap.height / ratio)
      ctx.lineWidth = 0.8
      ctx.strokeStyle = '#7ba88f'
      for (const item of paths) {
        const screen = project(item.path)
        ctx.fillStyle = item.fill
        ctx.fill(screen)
        ctx.stroke(screen)
      }
      ctx.strokeStyle = '#23725a'
      ctx.lineWidth = 1.8
      ctx.stroke(project(boundary))
      if (exterior) {
        ctx.lineJoin = 'round'
        ctx.lineCap = 'round'
        ctx.strokeStyle = MAP_COLORS.outline
        ctx.lineWidth = 2.4
        ctx.stroke(project(exterior))
        ctx.lineJoin = 'miter'
        ctx.lineCap = 'butt'
      }
      return true
    }
    function remove() {
      closed = true
      source.style.visibility = visibility
      bitmap.remove()
      bitmap.width = bitmap.height = 0
      active = null
    }
    try {
      if (!repaint()) return null
    } catch {
      return null
    }
    // The visualMap lives on its own canvas above this one; its position never moves.
    source.parentElement.insertBefore(bitmap, source.nextSibling)
    source.style.visibility = 'hidden'
    chart.dispatchAction({ type: 'hideTip' })
    active = {
      move(x, y) {
        if (closed) return
        dx += x
        dy += y
        if (Math.max(Math.abs(dx), Math.abs(dy)) > PADDING * 0.7) {
          // Rebase before exhausting overscan. This also permits arbitrarily long drags.
          pan(dx, dy)
          dx = dy = 0
          repaint()
        }
        bitmap.style.transform = `translate3d(${dx}px, ${dy}px, 0)`
      },
      finish() {
        if (closed) return
        try {
          pan(dx, dy)
        } finally {
          remove()
        }
      },
      cancel() {
        if (!closed) remove()
      },
    }
    return active
  }
  return {
    available: () => supported && !disposed && scene?.cells.length >= MIN_CELLS,
    begin,
    setScene(next) {
      active?.cancel()
      cancelIdle()
      scene = next
      paths = []
      cursor = 0
      if (supported && scene) schedule()
    },
    finish: () => active?.finish(),
    cancel: () => active?.cancel(),
    dispose() {
      disposed = true
      active?.cancel()
      cancelIdle()
      scene = null
      paths = []
    },
  }
}
