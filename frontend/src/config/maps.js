import hunan from '@/assets/hunan.geojson.json'
import tokens from '@/config/design-tokens.json'
const mapTokens = Object.assign({}, ...Object.values(tokens))

// Administrative identity and geometry come from the existing real GeoJSON.
// Sample counts are joined at runtime from /collection/summary, never fixtures.
export { hunan }
export const cityFeatures = Object.fromEntries(
  hunan.features.map((feature) => [String(feature.properties.adcode), feature]),
)
// Presentation anchors are geographic coordinates, never screen-pixel offsets.
// Yiyang's centroid falls in a narrow arm; use an interior visual center derived
// from the largest polygon's maximum-inscribed-circle point (tolerance 0.005°).
const labelAnchors = { 430900: [111.719913, 28.325237] }
export const cityMapConfig = Object.fromEntries(
  hunan.features.map((feature) => {
    const { adcode, name, center, centroid } = feature.properties
    const code = String(adcode)
    return [
      code,
      {
        code,
        name,
        shortName: name.replace(/市$/, '').replace('土家族苗族自治州', '州'),
        center: center || centroid,
        labelCenter: labelAnchors[code] || centroid || center,
        feature,
      },
    ]
  }),
)
// Both renderers register the same display cp without changing source geometry.
export const labeledHunan = {
  ...hunan,
  features: hunan.features.map((feature) => ({
    ...feature,
    properties: {
      ...feature.properties,
      cp: cityMapConfig[String(feature.properties.adcode)].labelCenter,
    },
  })),
}
export const MAP_COLORS = {
  empty: '#e8eeea',
  border: '#ffffff',
  selected: mapTokens['map-selected'],
  outline: '#5E8F79',
  scale: [0, 1, 2, 3, 4].map((i) => mapTokens[`map-scale-${i}`]),
}
// Province-wide visual quantiles only: the same metric/data batch has identical bins
// in overview and miniature maps. No statistical or business metric is recalculated.
export function mapColorScale(values, format = (v) => String(v)) {
  const sorted = values.filter((v) => Number.isFinite(v) && v >= 0).sort((a, b) => a - b)
  if (!sorted.length) return { pieces: [], color: () => MAP_COLORS.empty }
  const max = sorted.at(-1)
  const cuts = [
    ...new Set([1, 2, 3, 4].map((i) => sorted[Math.ceil((sorted.length * i) / 5) - 1])),
  ].filter((v) => v < max)
  const colors = cuts.length
    ? Array.from(
        { length: cuts.length + 1 },
        (_, i) => MAP_COLORS.scale[Math.round((i * 4) / cuts.length)],
      )
    : [MAP_COLORS.scale[2]]
  const pieces = [...cuts, Infinity].map((upper, i) => ({
    ...(i ? { gt: cuts[i - 1] } : { gte: 0 }),
    ...(Number.isFinite(upper) ? { lte: upper } : {}),
    label:
      i === 0
        ? cuts.length
          ? `≤ ${format(upper)}`
          : format(max)
        : Number.isFinite(upper)
          ? `> ${format(cuts[i - 1])} – ${format(upper)}`
          : `> ${format(cuts[i - 1])}`,
    color: colors[i],
  }))
  return {
    pieces,
    color: (value) =>
      !Number.isFinite(value) || value < 0
        ? MAP_COLORS.empty
        : colors[
            cuts.findIndex((v) => value <= v) === -1
              ? cuts.length
              : cuts.findIndex((v) => value <= v)
          ],
  }
}
export function mapHoverColor(color) {
  const rgb = color
    .slice(1)
    .match(/.{2}/g)
    .map((v) => parseInt(v, 16))
  return (
    '#' +
    rgb
      .map((v) =>
        Math.round(v + (255 - v) * 0.12)
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  )
}
export function mapLabelColor(color) {
  const channels = color
    .slice(1)
    .match(/.{2}/g)
    .map((v) => parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
  return luminance < 0.24 ? '#ffffff' : '#244b39'
}
