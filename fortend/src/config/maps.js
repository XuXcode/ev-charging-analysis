import hunan from '@/assets/hunan.geojson.json'

// Administrative identity and geometry come from the existing real GeoJSON.
// Sample counts are joined at runtime from /collection/summary, never fixtures.
export { hunan }
export const cityFeatures = Object.fromEntries(
  hunan.features.map((feature) => [String(feature.properties.adcode), feature]),
)
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
        labelCenter: centroid || center,
        feature,
      },
    ]
  }),
)
export const MAP_COLORS = {
  empty: '#edf2ef',
  border: '#ffffff',
  emphasis: '#174f3d',
  outline: '#6a9980',
  scale: ['#dcecdf', '#b8d6bc', '#86b898', '#4b9474', '#22664e'],
}
// Display bins, not a statistical model or density classification.
export const SAMPLE_CLASSES = [
  { lt: 500, label: '< 500', color: MAP_COLORS.scale[0] },
  { gte: 500, lt: 750, label: '500–749', color: MAP_COLORS.scale[1] },
  { gte: 750, lt: 1000, label: '750–999', color: MAP_COLORS.scale[2] },
  { gte: 1000, lt: 1500, label: '1,000–1,499', color: MAP_COLORS.scale[3] },
  { gte: 1500, label: '≥ 1,500', color: MAP_COLORS.scale[4] },
]
