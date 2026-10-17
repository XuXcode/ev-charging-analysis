// Map series use roam: 'scale'; only physical mouse dragging dispatches pan actions.
// `getTarget` keeps the roam target correct when a view switches between an internal
// map-series geo (regions) and an explicit geo component (grid + boundary overlays).
export function bindMapDrag(
  chart,
  element,
  getTarget = () => ({ componentType: 'series', seriesIndex: 0 }),
  getPreview = () => null,
) {
  let start = null
  let previous = null
  let moved = false
  let suppressClick = false
  let previewSource = null
  let preview = null
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
    if (preview) preview.move(dx, dy)
    else chart.dispatchAction({ type: 'geoRoam', ...getTarget(), dx, dy })
  }
  function end() {
    if (!start) return
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    // Apply the tail of the movement so the final position matches the cursor.
    commit()
    preview?.finish()
    preview = previewSource = null
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
    previewSource = getPreview()
    if (previewSource?.available()) event.stopImmediatePropagation()
    else previewSource = null
  }
  function move(event) {
    if (!start) return
    if (!(event.buttons & 1) || chart.isDisposed()) {
      end()
      return
    }
    const current = [event.clientX, event.clientY]
    if (!moved && Math.hypot(current[0] - start[0], current[1] - start[1]) < 4) return
    if (!moved && previewSource) {
      preview = previewSource.begin()
      if (!preview) previewSource = null
    }
    moved = true
    if (preview) event.stopImmediatePropagation()
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

  function blockPointerHover(event) {
    if (start && previewSource) event.stopImmediatePropagation()
  }
  function wheel() {
    if (start) end()
  }
  element.addEventListener('mousedown', down, true)
  window.addEventListener('pointermove', blockPointerHover, true)
  window.addEventListener('wheel', wheel, true)
  element.addEventListener('click', click, true)
  window.addEventListener('mousemove', move, { capture: true, passive: false })
  window.addEventListener('mouseup', end)
  window.addEventListener('blur', end)
  return () => {
    element.removeEventListener('mousedown', down, true)
    window.removeEventListener('pointermove', blockPointerHover, true)
    window.removeEventListener('wheel', wheel, true)
    element.removeEventListener('click', click, true)
    window.removeEventListener('mousemove', move, true)
    window.removeEventListener('mouseup', end)
    window.removeEventListener('blur', end)
    element.style.userSelect = previousUserSelect
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    preview?.cancel()
    preview = previewSource = null
    start = previous = null
    pendingX = pendingY = 0
  }
}
