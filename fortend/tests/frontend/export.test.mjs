import test from 'node:test'
import assert from 'node:assert/strict'
import {
  csvCell,
  toCsv,
  chartRows,
  exportChartCsv,
  clearPreparedDownload,
  preparedDownload,
} from '../../src/utils/export.js'
import { snapshotProvenance } from '../../src/utils/analysis-provenance.js'
test('CSV preserves zero, null and numeric precision and escapes formula text', () => {
  assert.equal(csvCell(0), '"0"')
  assert.equal(csvCell(null), '')
  assert.equal(csvCell(-0.008), '"-0.008"')
  assert.equal(csvCell('=HYPERLINK("example")'), '"\'=HYPERLINK(""example"")"')
  assert.equal(csvCell('  @SUM(1)'), '"\'  @SUM(1)"')
  assert.equal(toCsv([{ key: 'x', label: '样本' }], [{ x: 'a,b\nc' }]), '\ufeff"样本"\r\n"a,b\nc"')
})
test('export uses current ordered chart labels and raw values including quality warnings', () => {
  const rows = chartRows({
    xAxis: { name: '条/km²' },
    yAxis: { type: 'category', data: ['甲', '乙'] },
    series: [
      {
        type: 'bar',
        data: [{ value: 0.012345, cityCode: '430100', warning: true }, { value: null }],
      },
    ],
  })
  assert.equal(rows[0].region, '甲')
  assert.equal(rows[0].value, 0.012345)
  assert.equal(rows[0].unit, '条/km²')
  assert.match(rows[0].warning, /不完整/)
  assert.equal(rows[1].value, null)
})
test('scatter and array data preserve both axis values and units', () => {
  const rows = chartRows({
    xAxis: { name: '条/km²' },
    yAxis: { name: '%' },
    series: [{ type: 'scatter', data: [[0.02, 3], { value: [0.04, 5], regionName: '乙' }] }],
  })
  assert.deepEqual(
    rows.map((r) => [r.x, r.value]),
    [
      [0.02, 3],
      [0.04, 5],
    ],
  )
  assert.equal(rows[1].region, '乙')
  assert.equal(rows[0].unitX, '条/km²')
  assert.equal(rows[0].unit, '%')
})

test('CSV download constructs a UTF-8 blob with full evidence and releases the previous URL', async () => {
  const previousDocument = globalThis.document
  const previousCreate = URL.createObjectURL
  const previousRevoke = URL.revokeObjectURL
  const blobs = [],
    revoked = [],
    anchors = []
  URL.createObjectURL = (blob) => {
    blobs.push(blob)
    return `blob:test-${blobs.length}`
  }
  URL.revokeObjectURL = (url) => revoked.push(url)
  globalThis.document = {
    body: { append() {} },
    createElement(tag) {
      assert.equal(tag, 'a')
      const anchor = {
        click() {
          this.clicked = true
        },
        remove() {
          this.removed = true
        },
      }
      anchors.push(anchor)
      return anchor
    },
  }
  try {
    const provenance = snapshotProvenance({
      snapshotId: 's',
      computedAt: '2026-10-04T00:00:00Z',
      metadata: {
        runId: 'base',
        qualityRunIds: ['base', 'supplement'],
        datasetQualityRunIds: ['base', 'supplement'],
        parameters: { radiusM: 1000 },
        filters: { classification: 'personal' },
        frozenInputHash: 'hash',
        algorithmVersion: 'v1.2',
      },
    })
    const option = {
      yAxis: { type: 'category', data: ['区县'] },
      xAxis: { name: '条' },
      series: [{ type: 'bar', data: [0] }],
    }
    exportChartCsv(option, '真实比较', provenance)
    const content = await blobs[0].text()
    assert.match(content, /当前样本证据批次/)
    assert.match(content, /base \/ supplement/)
    assert.match(content, /冻结输入哈希/)
    assert.match(content, /radiusM/)
    assert.match(content, /personal/)
    assert.match(content, /"0"/)
    assert.equal(anchors[0].download, '真实比较.csv')
    assert.ok(anchors[0].clicked && anchors[0].removed)
    assert.equal(preparedDownload.value.url, 'blob:test-1')
    exportChartCsv(option, '再次比较', provenance)
    assert.deepEqual(revoked, ['blob:test-1'])
    clearPreparedDownload()
    assert.equal(preparedDownload.value, null)
    assert.deepEqual(revoked, ['blob:test-1', 'blob:test-2'])
  } finally {
    clearPreparedDownload()
    URL.createObjectURL = previousCreate
    URL.revokeObjectURL = previousRevoke
    if (previousDocument === undefined) delete globalThis.document
    else globalThis.document = previousDocument
  }
})
