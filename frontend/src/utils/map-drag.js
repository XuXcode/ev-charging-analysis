// Map series use roam: 'scale'; only physical mouse dragging dispatches pan actions.
export function bindMapDrag(chart, element) {
  let start = null
  let previous = null
  let moved = false
  let suppressClick = false
  const previousUserSelect = element.style.userSelect
  element.style.userSelect = 'none'

  function end() {
    if (!start) return
    suppressClick = moved
    start = previous = null
    moved = false
    if (!chart.isDisposed()) chart.getZr().setCursorStyle('grab')
  }
  function down(event) {
    if (event.button !== 0 || !event.target.closest('canvas')) return
    start = previous = [event.clientX, event.clientY]
    moved = suppressClick = false
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
    chart.dispatchAction({ type: 'geoRoam', componentType: 'series', seriesIndex: 0, dx, dy })
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
    end()
  }
}
