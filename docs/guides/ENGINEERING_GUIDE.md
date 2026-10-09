# 工程、数据字典与演示指南

这是现有Vue3 + FastAPI + MySQL工程的质量优化说明，不引入新后端架构。真实来源、公式和限制分别以COLLECTOR.md、POI_QUALITY.md、SPATIAL_METHODS.md为准。目录与部署以根README和DEPLOYMENT.md为准，本轮未运行测试或功能验证。

## 分层与生命周期

Vue路由懒加载三个视图，统一分析筛选由Pinia管理，URL负责恢复上下文。市州、区县、排名和图表选择共用状态；比较页面保留14市州背景，通过选中状态定位区域。Axios解包统一响应，保留HTTP状态和请求标识；取消请求不转成普通错误。ErrorBoundary捕获页面渲染异常，ViewState区分读取中、没有结果、待接入、错误与完整性警告。

MapView区分ECharts专题地图和高德站点地图，市州才加载地图SDK。ECharts通过core按需注册图表/组件，使用同一主题；实例、ResizeObserver、地图移动/缩放事件、定时器及旧请求在卸载时清理。成功边界按内容哈希缓存，避免不同版本混用。图层默认聚合，逐点Marker最多500个；当前视野加载450ms防抖，并取消旧请求。图表与地图PNG/CSV可导出，文件准备提示保留下载链接，关闭或下一次导出时释放ObjectURL。

FastAPI Router进行请求验证与响应组织，DataService处理领域读取，Repository投影/分页/批量关联质量记录；Collector和分析任务独立运行，GET不启动采集或昂贵空间计算。MySQL维护原始站点、采集原始页、质量派生记录、真实边界和分析快照；公开统计独立导入，不由POI推断。

## 主要数据字典

| 数据                                    | 标识与来源                        | 关键字段与口径                                                                                                                      |
| --------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| charging_stations                       | id主键；poi_id和identity_hash唯一 | adcode供应方原编码；longitude/latitude为GCJ-02；source=amap；collected_at为UTC采集时间；public_charger_count缺失保持null            |
| collection_runs / collection_pages      | run_id与行政区/页唯一             | manifest与原始POI、响应指纹、页状态、重试次数和返回上限；批次完成不保证供应方数据完整                                               |
| poi_quality                             | station_id一对一，不删除原记录    | classification五类、review_status三态、needs_review、reasons/evidence、confidence、rules_version、run_id、classified_at/reviewed_at |
| analysis_scope_quality                  | 区县adcode                        | completeness_warning指检索触及上限；false不表示普查完整                                                                             |
| analysis_boundaries                     | adcode与边界内容哈希              | 真实GeoJSON来源、坐标系、fetched_at；计算几何修复单独审计                                                                           |
| analysis_snapshots                      | snapshotId、run_id、input_hash    | algorithm_version、parameters、computed_at、result；包含来源日期、分类/状态筛选、指纹、边界、算法依赖与限制                         |
| statistic_snapshots / public statistics | 行政区与统计日期、独立来源        | 官方或可靠统计的站/桩/功率/年份及口径；当前可靠统计尚未接入，不用样本补齐                                                           |

API的source使用amap，UI显示高德开放平台。collectedAt与sourceUpdatedAt描述采集时间，不是建设年份或供应方更新日期。batch为采集/质量批次，snapshotId为派生分析版本，rulesVersion与algorithmVersion分别对应治理和几何分析。零表示确有空结果；null/—表示统计缺失；pending表示对应分析尚未接入。

## 可重复快照与筛选

完整公式见SPATIAL_METHODS.md。原始点不改址、不删除；基线纳入全部保留类别，过滤快照只对选中类别/状态建立同样的几何计算。每个快照保留全数据集指纹及范围指纹，筛选结果为空时占比无分母，不伪造比例。单一数据批次匹配时可复用对应范围快照；多批次数据需要显式生成批次范围，不能混用。源数据变化只标记过期，页面不自动运行分析。

```powershell
cd backend
.\.conda\python.exe -m app.services.analysis.scope_job
.\.conda\python.exe -m app.services.analysis.job --classification personal --review-status unreviewed
```

范围筛选参数已加入协议，几何公式仍为sample-spatial-v1.1，实现源码哈希随代码变化记录。24组合快照为真实计算，不是mock，不增加原始站点。

## 启动与部署

开发环境按根README和backend/README准备Node、Conda Python及MySQL。不要覆盖已有.env；对照.env.example补字段。前端VITE_AMAP_KEY与VITE_AMAP_SECURITY_JS_CODE（兼容旧名VITE_AMAP_SECURITY_CODE）用于浏览器JS API，后端AMAP_WEBSERVICE_KEY及DATABASE_URL留在backend/.env。前端JS凭据在浏览器可见，Web服务Key和数据库密码不得进入Vite变量或产物。

本地先启动MySQL与FastAPI，再运行npm run dev，以终端端口为准。生产部署前备份数据库、审核迁移并构建前端；部署dist静态文件时配置Vue history回退到index.html，反向代理/api至FastAPI，配置实际CORS域名。数据库、采集和分析任务不由网页请求启动；备份原始页、数据库、参数快照与环境配置。正式部署应使用本机或部署平台的进程管理器，不把开发服务器暴露为正式服务。

## 性能与安全复核

运行根目录`backend\.conda\python.exe scripts\audit-performance.py`只读审计数据库索引、EXPLAIN、三次HTTP耗时和压缩体积；结果写入PERFORMANCE_AUDIT.json。当前city分页1.45ms、county0.87ms、bbox0.90ms、分类0.53ms；状态1.90ms、采集日期3.54ms与排名5.83ms。MySQL选择主键顺序或现有复合索引，不强制低价值索引。分类使用classification/review_status/needs_review索引；review_status单独筛选扫描该索引，但目前低于2ms；时间汇总全表扫描约3.5ms，可靠统计表为空，尚无添加重复索引或Redis的证据。未来数据量增长后复测，不以小数据耗时代表生产容量。

只读安全扫描`backend\.conda\python.exe scripts\audit-secrets.py`输出位置与数量，永不输出凭据值。当前配置凭据在工作树和历史中的检查不等于对所有未知旧密钥的完全保证；必须结合模式检查、env忽略、前后端边界和产物审计。

## 比赛演示路径

1. 总览：展示14市州格局，解释“高德可检索POI样本”及真实核心发现；切换数量/密度/覆盖，地图和排行同步。
2. 空间格局：打开5km网格或描述性聚集，选择市州，查看区县与完整性约束。
3. 市州→区县：从排名或地图进入市州，展示聚合及信息窗，选择区县，说明真实样本来源与复核状态。
4. 可达性：展示1km几何覆盖、区县累计分布和低覆盖排名；说明这不是道路分钟可达性。
5. 薄弱区域：点选低覆盖区县定位未覆盖面，解释未覆盖不等于实际缺站，也未生成风险评级。
6. 供需与优化：展示独立问题结构和需要的可靠输入，待接入状态不当成已计算成果；导出当前真实图表与数据。

优先展示问题和真实结果，方法、完整快照ID、原始证据保留在说明或Drawer中。当前10745条样本、677条复核线索和17个触及上限区县都保留；不展示伪历史、伪桩数、道路时间、供需指数、优化收益或AI报告。
