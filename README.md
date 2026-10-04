# 湖南省新能源汽车充电基础设施空间分析与可视化平台

Vue 3 + JavaScript前端与 FastAPI 数据服务基座。以湖南地图为核心，为14市州提供统一空间展示和专题入口。
**默认使用真实接口；高德POI样本与官方设施统计分开展示。未接入的KPI显示“— / 统计数据待接入”，未实现的分析结果保持待接入。**

各菜单采用独立的信息结构：总览以地图为中心，空间格局使用地图与分析面板，可达性展示直线覆盖与分布，供需保留四象限，市州差异突出比较图，薄弱区域以清单定位，布局优化使用现状与方案对照。布局、统一筛选与本轮验证见[专题布局说明](docs/THEMATIC_LAYOUTS.md)。全项目优化的未完成验收项见[质量优化账本](docs/QUALITY_OPTIMIZATION.md)。

最新增量进度见[深度优化记录](docs/DEEP_OPTIMIZATION.md)：17区县补采后累计12,601条高德可检索POI样本（非官方设施总量），默认公共候选；支持全库搜索、区县比较、1km直线样本覆盖和冻结输入重放。原阶段10,745条记录保留用于历史追溯。道路专题已接入122区县代表点的真实5/10/15分钟驾车观测，详见[道路计算口径与验证](docs/ROAD_ACCESSIBILITY.md)；供需保持待接入；需求与 Greedy/MCLP 选址基座已实现，真实需求及新建候选缺失时不生成方案，见[需求与选址说明](docs/DEMAND_PLANNING.md)。

本轮十项要求的最终证据、性能前后对比、测试结果和已知限制见 [深度优化验收表](docs/DEEP_COMPLETION_AUDIT.md)。

## 安装与启动

本机主目录为 `R:\ev-charging-analysis`，支持 PyCharm 和 PowerShell 启动，见[本机启动与工程分层](docs/LOCAL_STARTUP.md)。

需要Node.js 20.19+或22.12+，推荐22/24 LTS。

```sh
npm install
cp .env.example .env.local
npm run dev
```

Windows PowerShell：

```powershell
npm.cmd install
Copy-Item .env.example .env.local
npm.cmd run dev
```

默认访问 http://localhost:5173 ，以终端实际输出端口为准。先按 [后端说明](backend/README.md)
启动 FastAPI，并配置前端 JS API Key 与后端 Web服务 Key。省级专题地图不依赖地图Key；市州站点地图需要有效JS API凭据。
未配置Web服务Key时采集器明确记录阻塞。地图读取已入库站点，不需要每次向高德检索。
本阶段真实数据链路的配置、采集和断点续跑见 [采集说明](docs/COLLECTOR.md)。

```sh
npm run check    # 模拟数据与14市州边界一致性
npm run build    # 构建输出到dist/
npm run preview  # 本地预览生产构建
npm run format  # 统一Vue、JavaScript和样式格式
npm run format:check # 检查格式
```

提交了package-lock.json，协作可使用`npm ci`安装一致依赖。部署服务器需配置Vue Router history回退：非静态资源请求返回`index.html`，确保深层路由可刷新。

## 技术栈与目录

Vue 3、JavaScript、Vite、Ant Design Vue、ECharts、高德JS API 2.0、Pinia、Vue Router、Axios。

```text
src/
  api/          # Axios与真实后端接口；站点不回退mock
  assets/       # 湖南14市州GeoJSON边界
  components/   # MapView、ChartContainer、MetricCard、RankingList、
                # CitySelector、DataSourceInfo、Loading、EmptyState
    maps/       # ProvinceMap（ECharts专题地图）、CityMap（高德站点地图）
  composables/  # useCityStations：市州/bbox查询、内部翻页、取消过期请求
  config/       # GeoJSON派生市州映射、地图色阶与图例
  mock/         # 业务模拟数据、专题和市州预留模块元信息
  router/       # 路由
  stores/       # Pinia跨页数据与排名状态
  styles/       # 全局布局、设计token与内容工作区样式
  utils/        # 高德加载器与图表配置
  views/        # 总览、市州详情、专题、404
docs/API_CONTRACT.md
scripts/check-fixtures.mjs
.env.example
```

协作约定：页面放`views`，复用交互放`components`，数据调用经过`api`，跨页数据放`stores`，模拟值集中在`mock`。地图和图表实例由组件管理并在卸载时销毁；ResizeObserver适配尺寸变化。

## 页面与交互

- `/`：核心指标、省级分级设色专题地图、14市州样本排名、真实样本对比、轻量数据状态卡与质量Drawer；历史趋势保持待接入。
- `/city/:cityCode`：14市州共享模板，基础指标、地图及七个分析模块：区县分布、热力、1km覆盖、5/10/15分钟可达性、供需、薄弱区域、布局优化。
- `/analysis/spatial`：空间格局分析。
- `/analysis/accessibility`：可达性分析。
- `/analysis/supply-demand`：供需协调分析。
- `/analysis/differences`：市州差异分析。
- `/analysis/underserved`：服务薄弱区域识别。
- `/analysis/optimization`：充电设施布局优化。
- 无效市州、专题或路径提供空状态/404及返回入口。

省级地图固定使用本地真实GeoJSON + ECharts Map，展示全部14市州边界、名称和高德可检索POI样本数量。Hover高亮及Tooltip展示样本数和全省样本占比，点击区域直接进入市州详情。右侧排名支持样本数量、样本密度与1km直线样本覆盖率切换，悬停或键盘焦点同步地图高亮和Tooltip。对比图采用同一真实汇总数据，不推算官方设施总量。

市州详情固定使用高德JS API 2.0，提供Marker、点聚合、等权POI热力、市州/区县边界、缩放、重置和全屏。站点只查询当前市州；开启“仅当前视野”后附加bbox，移动/缩放防抖重新加载。200条API分页由数据适配层内部消化，地图显示完整市州或视野结果，不提供列表翻页按钮。切换市州取消旧请求，地图卸载销毁图层和监听器。Key或网络不可用时显示错误及重试入口。

数据状态卡和质量Drawer读取现有`/collection/summary`，数量、更新时间与批次记录动态更新。默认按POI样本数量设色，可切换真实样本密度与1km直线样本覆盖率；地图、排名、图例和Tooltip共用指标。1920×1080为主要展示尺寸，普通桌面支持自然滚动，窄屏堆叠。

## 环境变量

| 变量                              | 默认 / 示例                    | 用途                             |
| --------------------------------- | ------------------------------ | -------------------------------- |
| `VITE_API_BASE_URL`               | `http://localhost:8000/api/v1` | Axios基础地址                    |
| `VITE_AMAP_KEY`                   | 空                             | 高德Web端JS API Key              |
| `VITE_AMAP_SECURITY_JS_CODE`      | 空                             | 演示开发安全密钥                 |
| `VITE_AMAP_SECURITY_SERVICE_HOST` | 空                             | 高德安全代理地址，配置后优先使用 |

复制`.env.example`为`.env.local`，修改后重启Vite。Key不写死在代码中，`.env.local`不进入Git。所有`VITE_`变量对浏览器公开，不能放后端秘密。正式部署按[高德安全密钥文档](https://developer.amap.com/api/javascript-api-v2/guide/abc/jscode)使用服务端代理；Loader遵循[JS API 2.0快速上手](https://developer.amap.com/api/javascript-api-v2/getting-started)，在加载前设置安全参数。

## 数据与后续接口替换

`src/mock/data.js`保留历史测试fixture；运行页面已不再导入模拟业务数据或模拟站点。
`src/mock/topics.js`只提供六类专题和七个市州模块的展示元信息。
独立采集器位于 `backend/app/services/collector/`，原始页面、清洗结果和批次断点保存在MySQL审计表。

FastAPI遵守[接口约定](docs/API_CONTRACT.md)，设置基础地址读取已入库数据；
配置CORS后即可联调。接口失败显示错误和重试，不自动回退模拟数据。

市州热力图已展示等权真实POI点的聚集强度；区县边界优先读取持久化真实边界，无快照时保留高德JS `DistrictSearch`后备。它们是地图展示图层，不是密度、覆盖或可达性分析。`MapView`读取独立快照中的1km直线样本覆盖；不运行道路等时圈、供需或优化算法。

边界来自[阿里云DataV.GeoAtlas湖南市州GeoJSON](https://geo.datav.aliyun.com/areas_v3/bound/430000_full.json)，下载日期2026-10-03。展示边界与模拟业务数据分开管理，正式使用前核验边界版本、使用许可和坐标系。

## 当前范围

前端页面与地图交互已保留，并新增 [FastAPI 后端基座](backend/README.md)。
当前使用真实接口：支持高德在线底图、14市州按区县分页采集、重试/限速/续跑、清洗去重、入库审计和前端站点联动。
未获取的业务统计显示“—”与“统计数据待接入”，不以0替代未知。已提供真实POI样本基础空间分析；道路专题提供代表点真实驾车观测，不包含人口/面积等时圈、供需指数、OR-Tools、AI及权限系统。
2026-10-03 已配置并验证两类高德 Key，完成长沙试采并续跑原14市州批次。
真实入库数量、排除原因与搜索上限以采集质量报告为准，不作为完整设施统计。

当前数据链路与结果见 [docs/COLLECTOR.md](docs/COLLECTOR.md)。原前端检查记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 两级地图展示层

保留浅色 + 湖南绿及原有「指标 / 样本概况 + 地图 + 排名 / 底部图表」结构：

- 省级看格局：14市州真实边界、分级设色、样本数与占比；点击进入原有`/city/:cityCode`路由。
- 市州看站点：按市州/bbox加载真实POI，提供聚合、Marker、热力及区县边界；返回全省恢复专题地图。
- 左侧仅展示可信的样本与来源口径，完整采集记录放入Drawer；排名和对比图与地图联动。
- 顶部存量指标预留同比、环比和SVG微趋势，只有相应可靠快照存在时显示。
- 市州对比按POI样本数量降序，虚线为14市州样本算术均值。
- 指标与分析口径入口解释单位、同比/环比、面积、分组与来源。底部同一容器预留密度散点、供需四象限、可达性分布；只显示数据等待状态。

当前指标和分组元信息由后端 `core/indicators.py` 提供；历史模拟fixture保留用于独立测试，不进入运行页面。入库POI数量与设施统计总量分开显示，不用POI条目推算官方设施总量、桩数或历史趋势；POI样本密度使用真实边界的模型面积，非官方设施密度。

实现边界、数据接口与本轮验证记录见[两级地图说明](docs/MAP_LAYERS.md)。专题布局调整读取已有接口，不修改真实数据采集逻辑；正式分析使用独立派生结构。

## POI 数据质量核验

数据质量抽屉新增原始类别、名称状态线索、开放范围线索和边界核验说明；站点信息窗明确营业状态尚未核验。结果来自现有数据库的离线只读核验，不是模拟统计。复核线索不用于自动删除样本。

运行 `.\backend\.conda\python.exe scripts/audit-poi-quality.py --verify-boundary-source` 生成质量快照与人工复核 CSV，然后运行 `npm.cmd run check:quality` 检查快照一致性和提示规则。发布前重新构建。具体结果、坐标口径与限制见 [POI 数据质量说明](docs/POI_QUALITY.md)。

## 第一版POI样本空间分析（已完成）

已新增独立治理表、分析快照与真实区县边界持久化结构，并执行真实样本保守分类。六类专题使用独立信息结构，保持真实API和原路由；未计算的分析结果仍显示待接入。已完成14市州/122区县统计、5km网格、描述性聚集、1km直线样本覆盖、区县钻取、快照复用、查询优化和独立CSV/JSON公开统计导入。第一版验收时110项后端测试通过；当前测试结果见全项目质量优化审计。任务与结果见[迭代记录](docs/ANALYSIS_ITERATION.md)、[方法公式](docs/SPATIAL_METHODS.md)、[统计导入](docs/PUBLIC_STATISTICS.md)和[完成审计](docs/COMPLETION_AUDIT.md)。

## 专题页面布局

专题采用“总览看地图，专题看问题”的信息结构：空间格局使用地图与分析面板，可达性使用覆盖指标与累计曲线，供需协调以四象限容器为主，市州差异以指标对比与散点为主，薄弱区域以清单与定位为主，布局优化以方案前后对照为主。现有真实快照用于密度与1km直线样本覆盖；道路专题另提供真实代表点驾车结果；供需结果保持待接入；布局优化已提供真实数据导入、Greedy/MCLP、双栏地图和冻结重放，实际方案等待需求与候选证据。详见 [专题布局说明](docs/TOPIC_LAYOUTS.md)。

## 全项目质量优化

统一三层Design Tokens、六项URL筛选、快照范围匹配、状态反馈和真实结果导出。工程结构、数据库字典、部署和比赛演示见[工程指南](docs/ENGINEERING_GUIDE.md)；接口见[API约定](docs/API_CONTRACT.md)。本轮验收记录见[质量优化审计](docs/QUALITY_OPTIMIZATION.md)，读写范围与后续限制见[空间方法](docs/SPATIAL_METHODS.md)。

## 需求与选址基座

新增需求标准化、设施候选筛选、有向OD缓存规划、Greedy/MCLP最大覆盖和离线方案重放。低可达性清单读取真实122区县代表点道路观测，并联动区县高德地图。新增模块不自动请求路线；数据契约、研究参考、方法边界及采样预算见[需求与选址说明](docs/DEMAND_PLANNING.md)。后端先安装更新后的 requirements.txt 并执行 `alembic upgrade head`。
