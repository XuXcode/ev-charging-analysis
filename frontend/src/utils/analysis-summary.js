import { classificationLabels, reviewStatusLabels } from '../config/analysis.js'
import { snapshotProvenance } from './analysis-provenance.js'
export function analysisSummary(snapshot, filters = {}) {
  if (!snapshot) throw new Error('当前分析快照待接入')
  const scope = filters.districtCode
    ? snapshot.districts.find((row) => row.code === filters.districtCode)
    : filters.cityCode
      ? snapshot.cities.find((row) => row.code === filters.cityCode)
      : snapshot.province
  if (!scope) throw new Error('当前行政范围没有匹配的分析结果')
  const name = scope.name || '湖南省'
  const metadata = snapshot.metadata
  const evidence = snapshotProvenance(snapshot)
  const number = (value) => (Number.isFinite(value) ? String(value) : '—')
  return [
    `${name}充电设施POI样本分析`,
    '来源：高德开放平台',
    `采集时间：${metadata.sourceUpdatedAt || '—'}`,
    `数据批次：${metadata.runId}`,
    `样本证据批次：${metadata.qualityRunIds?.join(' / ') || metadata.runId}`,
    `分析快照：${snapshot.snapshotId}`,
    `算法：${metadata.algorithmVersion}`,
    `算法名称：${evidence.algorithmName}`,
    `计算时间：${evidence.computedAt || '—'}`,
    `参数：${evidence.parameters}`,
    `冻结输入：${evidence.frozenInputHash || '历史版本未冻结完整输入'}`,
    `分类：${classificationLabels[filters.classification] || '全部保留类别'}`,
    `复核状态：${reviewStatusLabels[filters.reviewStatus] || '全部状态'}`,
    `待复核线索：${metadata.filters?.needsReview ? '仅规则线索，与当前类别取交集' : '不限线索'}`,
    `样本数量：${number(scope.count)}条`,
    `1km直线样本覆盖率：${number(scope.coveragePercent)}%`,
    `完整性：${scope.completenessWarning ? '检索触及上限，样本可能不完整' : '未触及检索上限不代表供应方收录完整'}`,
    '限制：GCJ-02米制近似；非官方设施总量或覆盖率；不代表道路可达性、容量、实际营业或人口覆盖。',
  ].join('\n')
}
