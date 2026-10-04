import { shallowRef } from 'vue'

export const preparedDownload = shallowRef(null)
export function clearPreparedDownload() {
  if (preparedDownload.value) URL.revokeObjectURL(preparedDownload.value.url)
  preparedDownload.value = null
}

// Keep raw numerical values; missing values stay empty. Neutralize spreadsheet formula text.
export function csvCell(value) {
  if (
    value === null ||
    value === undefined ||
    (typeof value === 'number' && !Number.isFinite(value))
  )
    return ''
  let text = String(value)
  if (typeof value !== 'number' && /^\s*[=+\-@\t\r]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}
export function toCsv(columns, rows) {
  return (
    '\ufeff' +
    [
      columns.map((c) => csvCell(c.label)).join(','),
      ...rows.map((row) => columns.map((c) => csvCell(row[c.key])).join(',')),
    ].join('\r\n')
  )
}
export function chartRows(option) {
  const rows = []
  for (const series of option?.series || []) {
    for (const [i, datum] of (series.data || []).entries()) {
      const data =
        typeof datum === 'object' && datum !== null && !Array.isArray(datum)
          ? datum
          : { value: datum }
      const vector = Array.isArray(data.value)
      const category =
        option.yAxis?.type === 'category' ? option.yAxis.data?.[i] : option.xAxis?.data?.[i]
      rows.push({
        series: series.name || series.type,
        region: data.regionName || category || data.name || '',
        code: data.regionCode || data.cityCode || data.code || '',
        x: vector ? data.value[0] : '',
        value: vector ? data.value[1] : data.value,
        unitX: vector ? option.xAxis?.name || '' : '',
        unit: option.yAxis?.name || option.xAxis?.name || '',
        warning: data.warning ? '检索触及上限，样本可能不完整' : '',
      })
    }
  }
  return rows
}
export function download(content, filename, type = 'text/csv;charset=utf-8') {
  clearPreparedDownload()
  const url = URL.createObjectURL(content instanceof Blob ? content : new Blob([content], { type }))
  const safeFilename = filename.replace(/[\\/:*?"<>|]/g, '-')
  preparedDownload.value = { url, filename: safeFilename }
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = safeFilename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
}
export function exportChartCsv(option, title, provenance = {}) {
  const rows = chartRows(option).map((row) => ({ ...row, ...provenance }))
  if (!rows.length) throw new Error('当前图表没有可导出的数据')
  const columns = [
    ['series', '序列'],
    ['region', '行政区或类别'],
    ['code', '行政编码'],
    ['x', '横轴值'],
    ['unitX', '横轴单位'],
    ['value', '数值或纵轴值'],
    ['unit', '数值单位'],
    ['warning', '完整性提示'],
    ['snapshotId', '分析快照'],
    ['batch', '数据批次'],
    ['qualityBatches', '当前样本证据批次'],
    ['datasetBatches', '完整数据集证据批次'],
    ['algorithmName', '算法名称'],
    ['algorithmVersion', '算法版本'],
    ['collectedAt', '数据集采集更新时间'],
    ['computedAt', '计算时间'],
    ['filters', '快照样本口径'],
    ['parameters', '算法参数与依赖版本'],
    ['frozenInputHash', '冻结输入哈希'],
    ['limitations', '已知限制'],
    ['source', '数据来源'],
  ].map(([key, label]) => ({ key, label }))
  download(toCsv(columns, rows), `${title}.csv`)
}
export async function exportChartPng(chart, title, subtitle = '', provenance = {}) {
  if (!chart) throw new Error('图表尚未准备好')
  const image = new Image()
  image.src = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  await image.decode()
  const canvas = document.createElement('canvas')
  canvas.width = image.width
  canvas.height = image.height + 270
  const context = canvas.getContext('2d')
  context.fillStyle = '#fff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = '#233b31'
  context.font = 'bold 28px Microsoft YaHei, sans-serif'
  context.fillText(title, 32, 42, canvas.width - 64)
  context.fillStyle = '#52685b'
  context.font = '22px Microsoft YaHei, sans-serif'
  context.fillText(subtitle, 32, 80, canvas.width - 64)
  context.drawImage(image, 0, 120)
  context.font = '18px Microsoft YaHei, sans-serif'
  context.fillText(
    [provenance.source, provenance.collectedAt, provenance.algorithmVersion]
      .filter(Boolean)
      .join(' · '),
    32,
    image.height + 156,
    canvas.width - 64,
  )
  if (provenance.batch)
    context.fillText(`数据批次：${provenance.batch}`, 32, image.height + 186, canvas.width - 64)
  if (provenance.qualityBatches)
    context.fillText(
      `样本证据批次：${provenance.qualityBatches}`,
      32,
      image.height + 216,
      canvas.width - 64,
    )
  if (provenance.snapshotId)
    context.fillText(
      `快照：${provenance.snapshotId} · 计算：${provenance.computedAt || '—'}`,
      32,
      image.height + 246,
      canvas.width - 64,
    )
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('图片导出失败，请重试')
  download(blob, `${title}.png`, 'image/png')
}
