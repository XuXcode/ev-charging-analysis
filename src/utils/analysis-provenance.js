/** Portable snapshot evidence; never derives statistics or substitutes current store filters. */
export function snapshotProvenance(snapshot) {
  const metadata = snapshot?.metadata
  if (!metadata) return {}
  return {
    snapshotId: snapshot.snapshotId || '',
    batch: metadata.runId || '',
    qualityBatches: (metadata.qualityRunIds || []).join(' / '),
    datasetBatches: (metadata.datasetQualityRunIds || []).join(' / '),
    algorithmName: 'POI空间分布与1km直线缓冲并集裁剪',
    algorithmVersion: metadata.algorithmVersion || '',
    collectedAt: metadata.sourceUpdatedAt || '',
    computedAt: snapshot.computedAt || '',
    filters: JSON.stringify(metadata.filters || {}),
    parameters: JSON.stringify(metadata.parameters || {}),
    frozenInputHash: metadata.frozenInputHash || '',
    source: '高德开放平台POI样本',
    limitations: metadata.notice || '样本非官方设施总量；直线覆盖非道路可达性。',
  }
}
