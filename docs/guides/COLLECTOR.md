# 湖南省充电站真实 POI 数据链路

沿用现有 FastAPI / SQLAlchemy / MySQL / Vue 架构。采集器是独立命令行模块，
不在 API 请求或前端 Hover 时运行。这里的“完成”指指定区县的有界关键词检索完成，
**不代表湖南充电设施全量普查**。

## 1. 申请与配置 Key

在[高德控制台](https://console.amap.com/dev/key/app)创建应用，分别添加：

- **Web 服务** Key：仅填写 `backend/.env` 的 `AMAP_WEBSERVICE_KEY`。
- **Web 端（JS API）** Key：填写根目录 `.env.local` 的 `VITE_AMAP_KEY`，
  对应安全密钥填写 `VITE_AMAP_SECURITY_JS_CODE`（也兼容 `VITE_AMAP_SECURITY_CODE`）。
  按控制台要求设置本地访问域名，生产部署使用 `VITE_AMAP_SECURITY_SERVICE_HOST` 安全代理。

两类 Key 不能混用；Web Service Key 不放到 VITE_ 变量。
`.env` / `.env.local` 已忽略 Git。修改配置后重启 Vite；后端修改后重启 FastAPI。
不要在命令行参数、截图、聊天或日志中粘贴真实密钥。

前端配置示例（空值需由用户在本地填写）：

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_AMAP_KEY=
VITE_AMAP_SECURITY_JS_CODE=
VITE_AMAP_SECURITY_SERVICE_HOST=
```

Web Service 验证命令会调用一次长沙行政区查询和一页芙蓉区 POI 搜索，不入库：

```powershell
cd backend
.\.conda\python.exe -m app.services.collector verify
```

成功输出 `webServiceVerified: true`。失败输出脱敏错误并返回退出码 2。
JS API 必须启动前端后在浏览器核验：地图状态为“在线底图”、底图加载正常、
没有 Key / 安全配置报错。REST 验证成功不等同于 JS Key 验证成功。

## 2. 迁移与采集

以下命令从 `backend` 执行，使用已有 Conda 环境：

```powershell
.\.conda\python.exe -m alembic upgrade head
.\.conda\python.exe -m app.db.import_regions
.\.conda\python.exe -m app.services.collector collect --interval 1 --retries 3
```

默认采集湖南14市州，先查询每个市州的区县清单，再按区县行政编码分页查询。
若行政区发现失败或清单异常，会停止并记录失败，不把该市州当作采集成功。
每区县固定关键词“充电站”，严格区域限制，每页25条，最多8页；短页或空页结束。
第8页满页时标记 `capped`，批次状态为 `completed_with_limits`。
不会通过网格拆分或轮换关键词绕过供应方返回上限。

先试采一个市州，或组合多个市州：

```powershell
.\.conda\python.exe -m app.services.collector collect --city 430100
.\.conda\python.exe -m app.services.collector collect --city 430100 --city 430200
```

默认请求间隔1秒；包括失败重试和行政区查询在内，所有请求统一限速。
`--interval` 至少0.2秒，具体值应符合自己的服务配额。网络失败、429、5xx及部分暂时性
高德错误最多重试3次，指数退避；无效 Key、权限和日配额错误停止采集。
不要把“有 Key”当作拥有相应接口调用权限；以验证返回和控制台服务配额为准。

## 3. 断点续跑与幂等

命令启动时输出32位批次 ID。断点存入 MySQL，不依赖命令执行的当前目录。

```powershell
.\.conda\python.exe -m app.services.collector collect --resume 批次ID
.\.conda\python.exe -m app.services.collector report 批次ID
```

续跑沿用批次冻结的范围、分页、限速和重试参数；不能同时修改市州范围。
行政区发现清单按市州保存。已提交页面不重新请求；未提交页面重新抓取。
站点 upsert、原始 POI、清洗结果和页面断点在同一个事务提交，提交前失败全部回滚。
进程意外关闭后的 `running` 批次也可续跑。已完成批次续跑不发起请求。
CLI 使用数据库连接级 `GET_LOCK`，阻止同一实例的采集命令并发写入。
此锁只约束 CLI 采集器，其他写入工具也须遵守数据一致性规则。

每次重新运行不带 `--resume` 会创建新批次，更新相同站点的采集时间，保留旧批次原始记录。
不会根据某一次检索未出现的 POI 删除已入库站点；当前库是累积去重清单，
最新批次去重数量与库内数量可能不同。
质量摘要按批次的最新活动时间排序，旧批次续跑后也能显示为最新记录。

## 4. 清洗规则与坐标

- 必须有非空 `poi_id`、名称、六位目标区县编码和有限经纬度。
- 结果须匹配请求区县和所属市州；经纬度须合法且位于宽松湖南合理性范围
  （108–115°E、24–31°N）。这只是异常值筛查，**不是**省界空间包含算法。
- 名称或类型须包含“充电站”；排除显式自行车、电瓶车、两轮和换电站记录。
  这是保守的 POI 筛选口径，可能遗漏名称/分类不规范的实际站点。
- Unicode NFKC 规范化、去空白和大小写规范化用于身份比较。
- 首先按 `poi_id` 匹配；其次按规范化名称 + GCJ-02 经纬度（保留6位小数）哈希去重。
  不做模糊名称匹配或距离聚类。不同 ID 的同名同坐标记录保留首个规范 ID，
  别名 ID 可在原始页面和清洗记录追溯。
- ID 与名称坐标指向不同已入库记录、来源冲突、跨市州 ID 冲突会记录异常，供人工核查。
- 坐标原值按数据库7位精度存储；**坐标系是 GCJ-02，不是 WGS84**。
- `source=amap`、`collected_at=本次采集 UTC 时间`，并关联非模拟 DataSource。
  采集时间不是供应方站点建设/更新日期。`public_charger_count=null`，不从 POI 名称推算桩数。

## 5. 记录、质量统计和 API

现有 `ChargingStation` 增加可空唯一 `identity_hash`；基础业务表保持原结构。
迁移新增两张审计表：

- `CollectionRun`：批次、状态、冻结配置、行政区发现清单、时间、脱敏失败原因。
- `CollectionPage`：批次/区县/页唯一键、请求次数、原始 POI JSON、响应 SHA-256、
  逐条清洗结果、关联站点 ID、页结束与触及上限标记。

质量报告按批次及市州提供：`rawCount` 原始数、`uniqueCount` 有效站点去重数、
`duplicateCount` 重复条目数、`rejectedCount` 排除/异常数、原因分类、
`insertedCount` / `updatedCount` / `mergedCount` 写入操作次数、已提交页数、触及上限区县。
恒等式：原始数 = 有效去重数 + 重复数 + 排除数。
写入操作次数不是独立站点数，同一站点在不同页面出现可能多次更新。
尚未发现/完成的区县和失败原因在报告中保留。

命令报告导出至忽略目录 `backend/.runtime/collector/<run_id>.json`，原始响应保存在数据库。
CLI 输出进度和脱敏错误，并自动保存 `.runtime/collector/<run_id>.log` 采集日志。

| GET API                            | 含义                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------------- |
| `/api/v1/stations`                 | 默认仅湖南真实高德入库站点，支持 city/adcode/bbox/keyword 和分页，page_size≤200 |
| `/api/v1/collection/summary`       | 库内真实累计去重数、14市州入库数、来源、UTC更新时间、最新批次质量报告           |
| `/api/v1/collection/runs/{run_id}` | 指定批次报告，未知批次404、非法ID422                                            |

接口遵循 `{code,message,data}`。旧测试联调可显式 `real_only=false`，
前端始终 `real_only=true`，不会回退站点 mock。总览与市州详情进入页面/切换市州自动读库，
每页最多200个 Marker，可翻页、刷新、查看来源与采集记录；不把第一页面当全部站点。
统计总量、公共充电桩、历史趋势、密度等仍只读取可靠统计快照；缺失显示“暂无数据”。
采集器不创建 StatisticSnapshot，不执行可达性、供需、OR-Tools、AI 或优化分析。

## 6. 本次实际结果与下一步

2026-10-03，迁移版本 `f233d458f264`。用户在本地配置凭据后，Web Service Key
通过行政区查询和 POI 搜索验证；JS API Key / 安全配置通过浏览器在线底图验证。
密钥未写入源码、日志或文档，配置文件已被 Git 忽略。

先实际试采长沙：批次 `7ef424b24cc248c78706a1ef5a0eb76b`，原始1,800条，
有效去重1,700条，重复71条，排除29条，9个区县均触及返回上限。
随后续跑此前因缺少 Key 阻塞的全省批次 `77751da1e930432394ebe8325068c3b6`，
本次续跑于北京时间22:34:55开始，22:43:33结束（数据库时间为 UTC）。

全省批次状态为 `completed_with_limits`：14市州、122个区县检索完成，
提交504页；原始 **11,282条**，有效去重 **10,745条**，重复 **427条**，
排除 **110条**，排除原因均为 `not_ev_charging_station`。
本批次新增9,045次、更新2,120次、别名合并7次；长沙试采已入库的1,700条再次更新，
没有重复插入。当前正式库累计10,745条，全部具有 POI ID、身份哈希、来源与采集时间。
504个 POI 页面均首个请求成功；失败重试与事务回滚另由隔离测试验证。

| 市州     | 原始记录 | 有效去重 / 当前入库 | 重复 | 排除 |
| -------- | -------: | ------------------: | ---: | ---: |
| 长沙市   |    1,800 |               1,700 |   71 |   29 |
| 株洲市   |      848 |                 805 |   37 |    6 |
| 湘潭市   |      605 |                 571 |   28 |    6 |
| 衡阳市   |      824 |                 815 |    5 |    4 |
| 邵阳市   |      775 |                 746 |   20 |    9 |
| 岳阳市   |      902 |                 821 |   70 |   11 |
| 常德市   |      729 |                 698 |   24 |    7 |
| 张家界市 |      489 |                 464 |   24 |    1 |
| 益阳市   |      644 |                 617 |   25 |    2 |
| 郴州市   |    1,038 |                 970 |   51 |   17 |
| 永州市   |      852 |                 823 |   23 |    6 |
| 怀化市   |      643 |                 628 |   10 |    5 |
| 娄底市   |      687 |                 650 |   32 |    5 |
| 湘西州   |      446 |                 437 |    7 |    2 |

17个区县触及200条返回上限：长沙9个区县，以及醴陵市、岳阳楼区、武陵区、永定区、
赫山区、北湖区、娄星区、新化县。其余区县以短页/空页结束也不证明供应方收录完整。
**这些数量仅表示关键词检索得到并通过当前规则的 POI，不是全省设施总量或运营站点总量。**
当前清单有100条名称含“暂停营业”或“已拆除”，保留供应方原始名称与审计记录，
尚未建立运营状态核验口径；部分名称/类别是否为汽车充电设施仍需人工抽查。

已实际核对 `/stations` 分页、市州/区县过滤、`/collection/summary` 及最新续跑批次。
正式库公共桩数均为空、统计快照0条，前端相应指标继续显示“暂无数据”。
后端 **64项测试通过**（实际MySQL，供应方异常由独立测试 transport 模拟），
前端 `npm run build` 通过，保留 ECharts 分包体积提示。
浏览器验证了1920×1080总览、详情路由、市州联动、200个 Marker、翻页、图层开关与来源弹窗。
修复在线模式下隐藏 ECharts 地图的零尺寸报错，以及续跑批次被较新试采批次遮蔽的问题。
截图见 [市州真实站点](../screenshots/live-city-poi.png) 和 [全省采集质量](../screenshots/live-province-quality.png)。

下一阶段建议先人工抽查分类、运营状态和重复合并，再结合可靠设施统计来源补充桩数，
核实触及返回上限区县的数据完整性。分析算法仍保持预留，待数据质量口径确定后再推进。

官方依据：[POI 2.0](https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch)、
[行政区域查询](https://lbs.amap.com/api/webservice/guide/api/district/)、
[JS安全配置](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode)。
