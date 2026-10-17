// Map series use roam: 'scale'; only physical mouse dragging dispatches pan actions.
// `getTarget` keeps the roam target correct when a view switches between an internal
// map-series geo (regions) and an explicit geo component (grid + boundary overlays).
export function bindMapDrag(chart, element, getTarget = () => ({ componentType: 'series', seriesIndex: 0 })) {
  let start = null
  let previous = null
  let moved = false
  let suppressClick = false
  let frame = 0
  let pendingX = 0
  let pendingY = 0
  const previousUserSelect = element.style.userSelect
  element.style.userSelect = 'none'

  // A single mouse drag emits far more mousemove events than the browser can paint
  // frames, and every roam action re-rasterises the whole 5km lattice. Merge the
  // deltas and dispatch at most one roam action per animation frame.
  function commit() {
    frame = 0
    const dx = pendingX
    const dy = pendingY
    pendingX = pendingY = 0
    if (!start || (!dx && !dy) || chart.isDisposed()) return
    chart.dispatchAction({ type: 'geoRoam', ...getTarget(), dx, dy })
  }
  function end() {
    if (!start) return
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    // Apply the tail of the movement so the final position matches the cursor.
    commit()
    suppressClick = moved
    start = previous = null
    moved = false
    if (!chart.isDisposed()) chart.getZr().setCursorStyle('grab')
  }
  function down(event) {
    if (event.button !== 0 || !event.target.closest('canvas')) return
    start = previous = [event.clientX, event.clientY]
    moved = suppressClick = false
    pendingX = pendingY = 0
  }
  function move(event) {
    if (!start) return
    if (!(event.buttons & 1) || chart.isDisposed()) {
      end()
      return
    }
    const current = [event.clientX, event.clientY]
    if (!moved && Math.hypot(current[0] - start[0], current[1] - start[1]) < 4) return
    moved = true
    const dx = current[0] - previous[0]
    const dy = current[1] - previous[1]
    previous = current
    chart.getZr().setCursorStyle('grabbing')
    pendingX += dx
    pendingY += dy
    if (!frame) frame = requestAnimationFrame(commit)
    event.preventDefault()
  }
  function click(event) {
    if (!suppressClick) return
    suppressClick = false
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  element.addEventListener('mousedown', down)
  element.addEventListener('click', click, true)
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', end)
  window.addEventListener('blur', end)
  return () => {
    element.removeEventListener('mousedown', down)
    element.removeEventListener('click', click, true)
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', end)
    window.removeEventListener('blur', end)
    element.style.userSelect = previousUserSelect
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    end()
  }
}
