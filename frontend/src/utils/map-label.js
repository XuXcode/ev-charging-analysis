import { formatNumber } from '@/utils/format'

// Name and sample count share one geographic anchor and identical line boxes.
export const cityLabelStyle = {
  position: 'inside',
  align: 'center',
  verticalAlign: 'middle',
  distance: 0,
  padding: 0,
  textBorderWidth: 0,
  rich: {
    city: {
      align: 'center',
      verticalAlign: 'middle',
      fontSize: 12,
      fontWeight: 500,
      lineHeight: 18,
      padding: 0,
    },
    count: {
      align: 'center',
      verticalAlign: 'middle',
      fontSize: 13,
      fontWeight: 600,
      lineHeight: 18,
      padding: 0,
    },
  },
}
export function cityLabelFormatter(params) {
  const name = params.data?.regionName || params.data?.shortName || params.name
  const count = params.data?.sampleCount ?? params.value
  return `{city|${name}}\n{count|${formatNumber(count, 0)}}`
}
