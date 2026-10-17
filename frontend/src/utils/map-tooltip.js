import { escapeHtml, formatNumber } from '@/utils/format'

// Grid density tooltip: count, effective area, density, hotspot status.
export function gridTooltip({ id, count, areaKm2, density, hotspot }) {
  return `<div class="map-region-tooltip">
    <strong class="map-region-tooltip__name">网格 ${escapeHtml(id)}</strong>
    <div class="map-region-tooltip__metric"><span>POI样本数</span><div><b>${formatNumber(count)}</b><small>条</small></div></div>
    <div class="map-region-tooltip__row"><span>有效面积</span><span>${formatNumber(areaKm2, 2)} km²</span></div>
    <div class="map-region-tooltip__row"><span>样本密度</span><span>${formatNumber(density, 3)} 条/km²</span></div>
    ${hotspot ? '<div class="map-region-tooltip__risk">描述性热点网格</div>' : ''}
  </div>`
}

// LISA tooltip: local statistic, permutation p and the FDR decision for this cell.
export function lisaTooltip({
  id,
  count,
  areaKm2,
  density,
  lisaClass,
  lisaClassLabel,
  localI,
  pSim,
  qFdr,
  significant,
  rawSignificant,
}) {
  const badge = lisaClass && lisaClass !== 'NS' ? `${lisaClassLabel} · ${lisaClass}` : '不显著'
  return `<div class="map-region-tooltip">
    <strong class="map-region-tooltip__name">网格 ${escapeHtml(id)}</strong>
    <div class="map-region-tooltip__row"><span>LISA类型</span><span>${escapeHtml(badge)}</span></div>
    <div class="map-region-tooltip__metric"><span>POI样本数</span><div><b>${formatNumber(count)}</b><small>条</small></div></div>
    <div class="map-region-tooltip__row"><span>样本密度</span><span>${formatNumber(density, 3)} 条/km²</span></div>
    <div class="map-region-tooltip__row"><span>有效面积</span><span>${formatNumber(areaKm2, 2)} km²</span></div>
    <div class="map-region-tooltip__row"><span>局部Moran's I</span><span>${Number.isFinite(localI) ? formatNumber(localI, 3) : '—'}</span></div>
    <div class="map-region-tooltip__row"><span>置换p值</span><span>${Number.isFinite(pSim) ? formatNumber(pSim, 4) : '—'}</span></div>
    <div class="map-region-tooltip__row"><span>FDR q值</span><span>${Number.isFinite(qFdr) ? formatNumber(qFdr, 4) : '—'}</span></div>
    ${
      significant
        ? '<div class="map-region-tooltip__risk">FDR校正后显著</div>'
        : rawSignificant
          ? '<div class="map-region-tooltip__row"><span>未校正p&lt;0.05</span><span>FDR后不显著</span></div>'
          : ''
    }
  </div>`
}

// Shared presentation only. Missing quality fields stay absent rather than invented.
export function regionTooltip({
  name,
  count,
  sharePercent,
  shareText,
  reviewCount,
  completenessWarning,
}) {
  const share =
    shareText ?? (Number.isFinite(sharePercent) ? `${formatNumber(sharePercent, 2)}%` : '—')
  return `<div class="map-region-tooltip">
    <strong class="map-region-tooltip__name">${escapeHtml(name)}</strong>
    <div class="map-region-tooltip__metric"><span>POI样本数</span><div><b>${formatNumber(count)}</b><small>条</small></div></div>
    <div class="map-region-tooltip__row"><span>占全省样本</span><span>${escapeHtml(share)}</span></div>
    ${Number.isFinite(reviewCount) && reviewCount > 0 ? `<div class="map-region-tooltip__row"><span>待复核线索</span><span>${formatNumber(reviewCount)} 条</span></div>` : ''}
    ${completenessWarning ? '<div class="map-region-tooltip__risk">样本可能不完整</div>' : ''}
  </div>`
}
export const regionTooltipStyle = {
  backgroundColor: 'rgba(247, 253, 249, 0.95)',
  borderColor: 'rgba(79, 132, 104, 0.25)',
  borderWidth: 1,
  padding: [12, 14],
  textStyle: { color: '#294b39', fontSize: 12 },
  extraCssText:
    'border-radius:12px;box-shadow:0 6px 20px rgba(25,65,45,.12);line-height:1.5;white-space:normal;',
}
