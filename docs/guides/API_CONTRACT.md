# 数据接口约定

沿用现有 FastAPI 分层服务。前端始终调用真实接口；没有站点 mock 回退。
成功：`{ "code": 200, "message": "success", "data": ... }`，Axios统一解包data。
错误：真实HTTP状态码和 `{code,message,data:{}}`，请求标识位于 `X-Request-ID` 响应头，不回传密钥或内部异常。
完整环境和启动见 [后端说明](../../backend/README.md)，采集规则见 [采集说明](COLLECTOR.md)。

## 统计与页面框架

- `GET /api/v1/dashboard`：cities、metrics、trend、sourceInfo、regions、cityTrends、
  analysisGroups、indicatorDefinitions、groupDefinitions、reservedCharts、stations、stationPage。
  stations仅提供首批兼容数据；地图独立调用分页站点接口，不依赖该数组。
- `GET /api/v1/overview`：metrics、sourceInfo、statisticDate。
- `GET /api/v1/regions`：14市州items、sourceInfo；`/regions/{adcode}`返回单个City。
- `GET /api/v1/rankings`：metric=station_count/public_charger_count/density。
- `GET /api/v1/trends?adcode=430000`：时间升序items、sourceInfo。
- `GET /api/v1/cities/{cityCode}/districts`：兼容旧接口，返回pending与空features；当前区县地图使用`/analysis/boundaries?parent=:cityCode`。
- `GET /api/v1/data-sources`：items、sourceInfo。

行政编码是六位字符串；City包含code/adcode/name/shortName/center/areaKm2/region和指标。
**stations/piles/density/fastRate/growth等统计缺失为null**，不是0。
没有可靠历史统计时trend为[]、yoy/qoq为null、sparkline为空。
这些数据只来自StatisticSnapshot及已核验面积，不用POI清单补造统计快照。
分组汇总只有所有成员数据已知时才返回数字，未知市州不被归到低值组。

## 真实入库站点

`GET /api/v1/stations`：

- city：市州名称、简称或编码；adcode：行政区编码；keyword：普通文本关键词。
- bbox：west,south,east,north；拒绝非法/NaN/无穷/反向范围。
- page≥1，page_size=1..200，默认20；排序按数据库id升序。
- real_only默认true：只返回湖南、source=amap且关联DataSource非模拟的站点。
  false仅用于显式旧数据测试，前端固定传true。
- classification：public_candidate/dedicated/personal/suspected_closed/unknown；review_status：unreviewed/confirmed/needs_review；batch：32位小写十六进制质量批次。参数取交集；未知批次404，非法参数422。没有质量记录的旧站点不混入分类结果。
- data：`{items,total,page,pageSize,sourceInfo}`。
  total是满足筛选条件的真实入库记录数，**不是当地充电设施普查总量**。

Station DTO：

```js
{
  id: '数据库ID', poiId: '高德POI ID', name: '站点名称', address: null,
  province: '湖南省', city: '长沙市', district: '实际区县名称',
  adcode: '实际区县编码', cityCode: '430100',
  position: [/* 高德GCJ-02经度, 纬度 */], type: '新能源汽车充电站',
  piles: null, source: 'amap', collectedAt: 'UTC ISO时间，带Z', simulated: false,
  classification: '保守分类或null', reviewStatus: '复核状态或null',
  confidence: '分类置信口径或null', needsReview: null,
  batch: '质量批次或null', rulesVersion: '治理规则版本或null', completenessWarning: false
}
```

sourceInfo包含simulated/updatedAt/period/label/boundary/note。
站点updatedAt是采集时间，不能解释为供应方原始数据更新时间或建设日期。
API支持分页传输；地图适配层内部读取当前市州/区县/bbox的所有页，每页200条，不提供列表式翻页。默认聚合，逐点Marker限定≤500条，超过时引导区县或视野筛选。
总览和市州切换自动读库；过期响应不能覆盖当前选择。

## 采集审计

- `GET /api/v1/collection/summary`：source、coordinateSystem=GCJ-02、simulated=false、
  storedCount（累计真实去重入库数）、updatedAt（UTC或null）、cities（14市州库内数量）、
  latestRun（报告或null）、notice。
- `GET /api/v1/collection/runs/{run_id}`：指定32位十六进制批次报告；未知404、非法422。

Run报告包含id/status/startedAt/updatedAt/finishedAt/lastError/manifest/totals/cities、
discoveredDistricts/finishedDistricts/cappedDistricts/notice。
状态：pending、running、blocked、failed、interrupted、completed、completed_with_limits。
completed仅表示该批次有界关键词检索执行完毕，不保证站点覆盖完整。

质量字段：rawCount、uniqueCount、duplicateCount、rejectedCount、insertedCount、
updatedCount、mergedCount、committedPages。cities中同时保留市州编码、名称、异常原因和上限区县。
原始数=有效去重数+重复数+排除数；写入操作次数与独立站点数不同。
批次量与累计库内量不同：重复采集会更新站点，不会因一次检索缺席删除历史入库记录。
manifest不含Key、密码或完整带Key请求URL。

## 保留的上游单页查询

`GET /api/v1/amap/status`仅表示后端Key是否已配置，不能证明Key有效。
`GET /api/v1/amap/stations?city=430100&page=1&page_size=25`仍可用于有界调试，
不入库，返回items/returnedCount/skippedCount/mayHaveMore/queriedAt/notice/sourceInfo。
前端地图不调用该接口；批量采集通过独立CLI，避免页面访问产生采集任务。
没有Key返回503，不回退测试地点。供应方失败502、超时504。

本阶段不注册或返回真实可达性、供需、选址优化、AI结果。

## 派生样本分析与质量

- `GET /analysis/latest`支持classification、review_status、needs_review、batch，返回匹配的已生成快照：snapshotId/computedAt/stale/metadata/province/cities/districts/indicatorDefinitions。needs_review是规则线索，与人工review_status独立。没有匹配结果404，禁止退回全样本。
- metadata包含sourceUpdatedAt、runId、qualityRunIds、datasetQualityRunIds、algorithmVersion、参数口径、输入指纹、冻结输入哈希、边界哈希、网格与归属审计。已生成48种类别/状态/规则线索组合，零样本组合有真实空结果。额外批次筛选没有快照时明确待接入；仅当未限定批次快照整个数据集只含请求的一个证据批次时可复用该结果。
- 快照完整输入保存在数据库供离线重放，API不返回frozenInputs或未请求的图层。图层接口必须使用最新结果的snapshotId固定版本，避免跨口径混用。
- `GET /analysis/boundaries?parent=430000`返回14市州，parent为市州编码时返回区县，未知范围404。
- `GET /analysis/layers/{grid|hotspots|coverage|uncovered}`支持固定snapshot_id、city、adcode、bbox；结果按请求范围裁选，不在GET执行缓冲或网格计算。边界/快照不存在404，越市州及非法bbox422。
- `GET /quality/pois`支持类别、复核状态、batch、adcode、bbox、keyword、needs_review、all_records及page/page_size，返回原始证据、保守分类与完整性提示。默认复核线索视图，all_records=true查全部保留POI。
- 所有URL以上述`/api/v1`为前缀。完整交互文档为运行服务的`/docs`，OpenAPI为`/openapi.json`。
