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
  function sync() {
    if (chart.isDisposed()) return
    const visible = enabled() && Boolean(chart.getOption()?.series?.[0]?.map)
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
  chart.on('rendered', sync)
  return () => {
    chart.off('rendered', sync)
    if (!chart.isDisposed()) chart.getZr().remove(group)
  }
}
