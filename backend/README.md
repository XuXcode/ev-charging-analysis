# 湖南充电空间分析数据服务

本目录是 FastAPI 后端基座。使用 Conda + Python 3.12，MySQL 8、SQLAlchemy 2、Alembic。
已提供统计快照读取、行政区查询、站点检索和按市州发起的高德地点搜索。
已增加独立行政区分页采集器、清洗去重、页面断点和质量审计。
独立任务提供POI样本密度、5km网格、描述性聚集和1km直线样本覆盖；独立道路任务新增122区县内部代表点到候选POI的真实驾车观测，见[道路说明](../docs/guides/ROAD_ACCESSIBILITY.md)。未实现人口/面积等时圈、供需、AI或权限系统。新增需求与 Greedy/MCLP 选址基座，真实输入缺失不生成实际方案，见[需求与选址说明](../docs/guides/DEMAND_PLANNING.md)。
运行和配置详情见 [真实数据链路说明](../docs/guides/COLLECTOR.md)。

默认连接真实接口，业务统计缺失时返回 null / 空序列，前端显示“暂无数据”。
地点搜索条目不用于填充官方设施总量、充电桩数量或历史趋势；POI样本密度单独标明真实边界模型口径。

## Conda 环境

推荐 Python 3.12；本机实际验证版本是 3.12.14。Conda 环境与前端 Node 环境独立。
从项目根目录进入 backend，在 Anaconda Prompt 或已经初始化 Conda 的终端运行：

```powershell
cd backend
conda env create --prefix .\.conda --file environment.yml
conda activate .\.conda
python --version
python -m pip check
```

environment.yml 固定 Python 3.12，使用 requirements.txt 安装 Python 包。
如需复现本轮 Windows / Python 3.12 验证过的精确依赖版本：

```powershell
python -m pip install -r requirements.lock.txt
```

也可先执行 `conda create --prefix .\.conda python=3.12 pip -y`，
激活后执行 `python -m pip install -r requirements.txt`。不在 base 环境安装项目依赖。
已有本机 backend/.conda 可以直接激活，不需要重复创建。
如果当前终端没有 conda 命令，使用 Anaconda Prompt；本机 Conda 位于
`C:\Users\84113\anaconda3\Scripts\conda.exe`。未激活时可从 backend 执行
`.\.conda\python.exe -m pytest -q` 等命令。

环境目录、.env、MySQL 临时数据目录、缓存均已排除 Git。
requirements.lock.txt 是本轮依赖版本记录，不含 Key 或数据库密码。

## MySQL 与环境变量

安装并启动 MySQL 8（本轮在 8.4.8 验证），用管理员连接执行：
替换下列占位密码后使用，仅对应用和独立测试库授权。

```sql
CREATE DATABASE ev_charging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE ev_charging_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ev_app'@'localhost' IDENTIFIED BY 'replace_me';
GRANT ALL PRIVILEGES ON ev_charging.* TO 'ev_app'@'localhost';
GRANT ALL PRIVILEGES ON ev_charging_test.* TO 'ev_app'@'localhost';
```

```powershell
Copy-Item .env.example .env
```

修改 backend/.env：

| 变量                                             | 用途                                                                |
| ------------------------------------------------ | ------------------------------------------------------------------- |
| DATABASE_URL                                     | mysql+pymysql://用户名:URL编码密码@主机:端口/数据库?charset=utf8mb4 |
| TEST_DATABASE_URL                                | 独立 MySQL 测试库，库名必须以 _test 结尾，不能与应用库相同          |
| AMAP_WEBSERVICE_KEY                              | 高德“Web服务 API”类型 Key，仅保存在后端                             |
| CORS_ORIGINS                                     | JSON 数组形式的前端地址白名单，含端口                               |
| ENVIRONMENT                                      | development / production；production 禁止导入测试数据               |
| LOG_LEVEL                                        | INFO / WARNING 等                                                   |
| DB_POOL_SIZE / DB_MAX_OVERFLOW / DB_POOL_RECYCLE | 连接池大小、额外连接数、回收秒数                                    |
| APP_NAME                                         | Swagger 标题                                                        |
| DEBUG                                            | 保留配置字段；HTTP 错误始终隐藏内部调试细节                         |

配置基于 backend/.env 的绝对位置读取，不依赖启动时的当前目录。
环境变量优先于 .env。密码包含 @、/、:、% 等字符时需要 URL 编码。
数据库地址使用 SecretStr；日志不打印 SQL 参数、高德 Key 或完整外部请求 URL。
DATETIME 按 UTC 存储；高德查询返回带 UTC 时区的请求时间，不冒充供应方数据更新时间。

本次验证使用项目内独立的 MySQL 数据目录 backend/.runtime/mysql，监听 127.0.0.1:23306，
应用库 ev_charging_live、测试库 ev_charging_test，未改动已有 MySQL 服务。
本机 backend/.env 已配置该实例，生成的私有凭据只在忽略目录保存。
换电脑应按上面步骤创建自己的 MySQL 库，重新配置 .env。
该临时实例不是 Windows 服务，重启电脑后需重新启动它或改用自己的 MySQL 服务；
启动命令可参考 backend/.runtime/README.md。

## 迁移、行政区导入与启动

所有以下命令在 backend 且激活 Conda 环境后执行：

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic check
python -m app.db.import_regions
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

import_regions 导入湖南省及14市州的行政代码、名称和地图展示中心。
元信息来自仓库现有 DataV GeoJSON，省级中心为视角定位点。
不导入模拟设施、估算面积或统计快照。重复执行不创建重复行政区，
也不覆盖已经存在的行政区；遇到旧模拟行政区会拒绝执行，需使用独立空库。
启动只检查数据库连接，不自动建表、迁移或写入任何数据。

- Swagger：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI：[http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

新增模型字段后执行 `python -m alembic revision --autogenerate -m "说明"`，
审查生成的脚本后执行 upgrade。check 用于检查模型与当前数据库是否一致。
`python -m alembic upgrade head --sql` 可以生成离线 SQL。
downgrade 会删除对应表和数据，只用于可重建测试库；不要在业务库随意回滚。
本轮已经在独立测试库实际验证 downgrade base → upgrade head → check。

## 高德接入与前端联调

申请两种用途不同的 Key：

1. fortend/.env.local 的 VITE_AMAP_KEY：Web端（JS API）Key。
   设置 VITE_AMAP_SECURITY_JS_CODE，或使用 VITE_AMAP_SECURITY_SERVICE_HOST 安全代理。
2. backend/.env 的 AMAP_WEBSERVICE_KEY：Web服务 API Key，供后端地点查询使用。

前端配置：

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_AMAP_KEY=your_js_api_key
VITE_AMAP_SECURITY_JS_CODE=your_security_code
```

修改后分别重启 Vite 与 FastAPI。高德 JS 安全密钥正式部署建议使用服务端代理；
不要把 Web服务 Key 放进 VITE_ 变量或提交仓库。

在总览或 /city/:cityCode 自动读取 `/stations` 真实入库站点，点击“刷新站点”更新，
接口内部每页最多200条，地图按市州或bbox加载，不提供列表翻页按钮。切换市州清除旧站点，过期响应不会覆盖新选择。
Hover和页面访问不发起高德POI查询。地图“数据来源与采集记录”展示库内数量和最新批次质量。
保留 `/amap/stations` 单页检索接口用于调试，前端主流程不再调用该接口。
2026-10-03 两类 Key 已验证，原 blocked 批次已在配置凭据后续跑。
实际结果见 [采集说明](../docs/guides/COLLECTOR.md)；入库清单不代表完整设施总量。

公开 POI 2.0 不保证完整站点普查，同一搜索参数最多获取200条，每页1–25条。
API 返回 returnedCount（当前页有效地点数），不返回伪造的全市总量。
mayHaveMore 只表示可能有下一页，不保证搜索完整性。
缺少坐标、越界坐标和不属于目标市州的结果被剔除，并返回 skippedCount。
piles 为 null；不会从名称猜测桩数、快慢充比例或建设历史。查询不自动入库。
地图坐标按高德返回值展示；后续导入其他坐标来源时应明确坐标系再转换。

## API 与响应

```json
{ "code": 200, "message": "success", "data": {} }
```

所有数据 API 使用统一外层结构；HTTP 错误保持真实状态码。
404 为未知行政区 / 路由，422 为非法参数，503 为数据库或缺失高德配置，
502 / 504 为高德响应失败 / 超时，500 为未预期错误。
响应含 X-Request-ID，日志用于关联请求，不回传内部异常或上游 Key。

| GET 路由                          | data 结构 / 参数                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------- |
| /api/health                       | status、database，实际 SELECT 1                                                        |
| /api/v1/overview                  | metrics、sourceInfo、statisticDate                                                     |
| /api/v1/regions                   | items（14市州）、sourceInfo                                                            |
| /api/v1/regions/{adcode}          | City，保留前端 code / stations / piles 等字段                                          |
| /api/v1/rankings                  | metric、unit、items、sourceInfo；metric=station_count / public_charger_count / density |
| /api/v1/trends                    | adcode、items、sourceInfo；默认430000，时间按数据库快照升序                            |
| /api/v1/stations                  | items、total、page、pageSize、sourceInfo；仅查询已入库站点                             |
| /api/v1/data-sources              | items、sourceInfo                                                                      |
| /api/v1/dashboard                 | 原 Vue 总览聚合对象，由数据库记录组装                                                  |
| /api/v1/cities/{adcode}/districts | pending、空features，不返回伪造区县结果                                                |
| /api/v1/amap/status               | configured，不暴露 Key                                                                 |
| /api/v1/amap/stations             | city（六位市州编码）、page、page_size；items / returnedCount / notice 等               |
| /api/v1/collection/summary        | 真实累计入库数、14市州入库数、来源和最新采集批次报告                                   |
| /api/v1/collection/runs/{run_id}  | 指定批次原始/去重/异常/市州数、已提交页和截断状态                                      |

stations 默认 `real_only=true`，排除演示记录；旧测试可显式 false。
支持 city 名称 / 简称 / 市州编码、adcode、keyword、
bbox=west,south,east,north、page、page_size（最多200）。
city 与 adcode 冲突返回422；bbox 拒绝 NaN、无穷、越界与反向范围。
关键词按普通文本搜索，不把 % 或 _ 当作通配符。

统计 API 仅读取已保存的 StatisticSnapshot；不会按 Marker 数量补造统计。
密度为已入库存量 / 已核验面积 × 100 的指标格式化，不涉及空间覆盖算法。
同比 / 环比仅在相应历史快照存在时返回，缺失为 null。
未知与真实零值区别处理；缺少面积返回 null，空趋势为 []。
当前线上联调库只有行政区信息，全部业务统计为空。
完整统计未接入时市州列表保留空值，不声称已经产生有效排名。
前端 Axios 已兼容外层响应，不需要修改主要页面结构。

## 测试

```powershell
python -m pytest -q
python -m ruff check app alembic tests
python -m ruff format --check app alembic tests
python -m pip check
```

pytest 必须使用专用 MySQL 测试库，不用 SQLite 替代、不静默跳过数据库检查。
测试先迁移，再将各用例置于独立事务 / savepoint，结束后回滚。
测试 fixture 的少量虚构字段只用于自动化校验，不进入应用数据库或真实界面。
高德适配测试使用 MockTransport 校验字段、边界和异常，不消耗真实调用配额。
当前110个用例通过；目前上游 Starlette TestClient 对 httpx 有1条弃用提示，测试无失败。
新增测试覆盖重试、限速、清洗去重、14市州分离、触及200条上限、断点续跑、页事务回滚和真实站点API。

如需要单独验证旧前端模拟模式，测试 fixture 保存在 app/db/fixtures/dashboard.json，
可显式执行 `python -m app.db.seed --demo`，但不要对真实联调库执行。
生产环境禁止该命令；默认启动流程完全不运行它。

## 项目结构与后续扩展

```text
backend/
  app/
    api/health.py          健康检查
    api/dependencies.py    请求级 Session 与服务依赖
    api/v1/router.py       统计、行政区、站点和总览适配
    api/v1/amap.py         有界高德查询入口
    api/v1/analysis/       routes.py已注册快照/边界/图层；正式扩展模块保留
    core/                 Settings、日志、异常、指标说明
    db/                   Base、Session、行政区导入与测试fixtures
    models/               Region / ChargingStation / StatisticSnapshot / DataSource
    schemas/              统一响应、分页、DTO与采集入参
    repositories/         SQL筛选、分页、分批读取、POI幂等写入
    services/             已入库数据读取、高德查询、前端聚合
    services/collector/   独立CLI、限速重试client、cleaning、原子页runner与质量报告
    services/analysis/    几何计算、快照任务、数据读取与只读运行审计
    utils/                日期和bbox校验
    main.py               应用工厂与生命周期
  alembic/versions/       已实际验证的基础表迁移
  tests/                  真实MySQL + HTTP契约测试
  environment.yml        Conda环境
  requirements.txt       兼容范围
  requirements.lock.txt  本轮已验证的精确版本
  .env.example           无真实密钥的配置示例
```

4张业务表只增加少量必要字段：行政区简称 / 分组 / 已核验面积、
演示标记、站点桩数（允许为空）、数据来源外键和常用索引。
采集器使用 StationCreate 校验后按POI ID和名称/坐标身份写入现有 ChargingStation，
新增 CollectionRun / CollectionPage 两张审计表，提交页事务同时保存原始记录与断点。
没有写入伪造 StatisticSnapshot，详细规则见 docs/COLLECTOR.md。
正式分析任务读取站点投影字段、质量与真实边界，持久化AnalysisSnapshot，记录输入、参数、算法和来源版本；相同输入复用快照。新增PoiQuality、AnalysisBoundary、AnalysisScopeQuality和PublicStatistic为独立派生/统计结构，原始站点全部保留。
公开统计CLI、原子校验及来源口径见[导入说明](../docs/guides/PUBLIC_STATISTICS.md)。真实库公开统计为0条，没有补造统计。分析命令与公式见[空间方法](../docs/guides/SPATIAL_METHODS.md)，完成证据见[审计](../docs/history/COMPLETION_AUDIT.md)。
实际分析接口由 analysis/routes.py、accessibility.py 和 planning.py 注册；无代码且未注册的旧占位文件已清理，
不会返回模拟分析结果。没有 Redis、Celery、JWT 或 GeoPandas；选址模块使用 SciPy milp/HiGHS，不使用 OR-Tools。

参考：[FastAPI Settings](https://fastapi.tiangolo.com/advanced/settings/)、
[SQLAlchemy MySQL](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)、
[Alembic迁移](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)、
[高德POI 2.0](https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch)、
[高德JS安全密钥](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode)。
