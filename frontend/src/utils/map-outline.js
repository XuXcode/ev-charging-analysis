import { graphic } from 'echarts/core'
import outline from '@/assets/hunan-outline.json'
import { MAP_COLORS } from '@/config/maps'

// An independent stroke layer uses the PRIMARY map's coordinate transform.
// It has no fill, labels, hit targets or second camera, so pan/zoom cannot drift.
export function bindProvinceOutline(chart, enabled = () => true) {
  const group = new graphic.Group({ silent: true, z: 6 })
  const paths = outline.rings.map(
    () =>
      new graphic.Polyline({
        z: 6,
        z2: 100,
        silent: true,
        style: {
          stroke: MAP_COLORS.outline,
          fill: null,
          lineWidth: 2.4,
          lineJoin: 'round',
          lineCap: 'round',
        },
      }),
  )
  paths.forEach((path) => group.add(path))
  chart.getZr().add(group)
  let lastTransform = ''

  // `rendered` fires on every roam frame. Reading the option here with
  // `chart.getOption()` deep-clones the whole option — 8895 grid features with
  // itemStyle/emphasis/label objects — which dominated the drag cost. Probe the
  // already-parsed series model instead: same answer, no allocation.
  function mapSeriesReady() {
    const model = chart.getModel?.()
    if (!model?.getSeriesByIndex) return Boolean(chart.getOption?.()?.series?.[0]?.map)
    const series = model.getSeriesByIndex(0)
    return Boolean(series && series.get('map'))
  }

  function sync() {
    if (chart.isDisposed()) return
    const visible = enabled() && mapSeriesReady()
    if (group.ignore === visible) group.attr('ignore', !visible)
    if (!visible) {
      lastTransform = ''
      return
    }
    // MapChart's default geographic projection is affine. Reuse the exact transform
    // and avoid projecting all vertices again on tooltip/highlight-only redraws.
    const origin = chart.convertToPixel({ seriesIndex: 0 }, [110, 26])
    const east = chart.convertToPixel({ seriesIndex: 0 }, [111, 26])
    const north = chart.convertToPixel({ seriesIndex: 0 }, [110, 27])
    if (![origin, east, north].every((p) => p?.every(Number.isFinite))) return
    const signature = [...origin, ...east, ...north].join(':')
    if (signature === lastTransform) return
    lastTransform = signature
    outline.rings.forEach((ring, i) =>
      paths[i].setShape({
        points: ring.map(([lng, lat]) => [
          origin[0] + (lng - 110) * (east[0] - origin[0]) + (lat - 26) * (north[0] - origin[0]),
          origin[1] + (lng - 110) * (east[1] - origin[1]) + (lat - 26) * (north[1] - origin[1]),
        ]),
      }),
    )
  }
  // A roam changes the projection, so the outline must be reshaped too. Doing that
  // from `rendered` would dirty the canvas again right after a full paint and force
  // a second complete repaint of every region (measured: 2x canvas work per drag
  // step). `georoam` fires while the action is still being applied — before the
  // frame is painted — so the new shape lands in the same repaint.
  chart.on('georoam', sync)
  chart.on('rendered', sync)
  return () => {
    chart.off('rendered', sync)
    if (!chart.isDisposed()) chart.getZr().remove(group)
  }
}
