# 湖南省新能源汽车充电设施空间分布与可达性可视化分析平台

基于真实高德可检索POI样本，展示湖南省14市州、122区县的空间格局与代表点道路可达性。采用 Vue 3 + JavaScript + FastAPI + MySQL，保留浅色湖南绿界面。

## 正式功能

| 页面       | 核心能力                                             |
| ---------- | ---------------------------------------------------- |
| 全省总览   | 14市州专题地图、POI样本指标、排名及地图联动          |
| 空间格局   | 密度、5km网格、描述性热点、1km直线样本覆盖           |
| 可达性分析 | 122区县代表点道路观测、5/10/15分钟阈值及低可达性清单 |
| 市州差异   | 市州与区县真实数量、密度、直线覆盖对比               |

共享省→市州→区县→站点钻取、全库搜索、条件筛选、质量追溯和PNG/CSV/快照导出。省级地图使用ECharts与真实GeoJSON；市州和区县使用高德JS API 2.0，提供站点、聚合、热力与边界图层。

POI样本不代表官方设施总量或已确认营业设施。1km直线覆盖是模型几何面积比例；区县代表点道路结果不代表全区县人口或面积覆盖。缺失观测单列，不补造统计。

## 技术栈与目录

前端：Vue 3、JavaScript、Vite、Ant Design Vue、ECharts、Pinia、Vue Router、Axios、高德JS API。后端：FastAPI、SQLAlchemy、Pydantic、HTTPX、Shapely、PyProj、Alembic、MySQL 8。

```text
ev-charging-analysis/
├── frontend/
│   ├── src/
│   │   ├── views/            四页与市州详情
│   │   ├── components/      通用、地图与分析组件
│   │   ├── api/             Axios接口适配
│   │   ├── stores/          Pinia状态与筛选
│   │   ├── router/          路由与页面加载
│   │   ├── config/          市州映射、指标与视觉配置
│   │   ├── assets/          真实GeoJSON与资源
│   │   ├── utils/           图表、格式和导出工具
│   │   └── styles/          统一样式
│   ├── public/              静态资源与质量资料
│   ├── scripts/             设计token生成
│   └── .env.example
├── backend/
│   ├── app/
│   │   ├── api/             Router和请求依赖
│   │   ├── services/        业务、采集及空间/道路分析
│   │   ├── repositories/    数据读取与分页
│   │   ├── schemas/         请求和响应契约
│   │   ├── models/          SQLAlchemy模型
│   │   ├── db/              数据库会话、真实行政区元数据
│   │   ├── core/            配置、日志与错误处理
│   │   └── utils/
│   ├── alembic/             保留的迁移历史
│   ├── requirements.txt     运行依赖
│   ├── requirements-dev.txt Ruff开发工具
│   ├── requirements.lock.txt 运行版本参考
│   └── .env.example
├── scripts/                 启动、采集治理与只读密钥审查
├── docs/                    来源、方法、接口与部署说明
└── package.json             前端命令转发
```

## 安装与配置

需要 Node.js 20.19+ 或22.12+、Conda Python 3.12、MySQL 8。在根目录运行：

```powershell
npm.cmd run install:frontend
conda env create --prefix .\backend\.conda --file .\backend\environment.yml
```

只在配置不存在时，从 `frontend/.env.example` 创建 `frontend/.env.local`，从 `backend/.env.example` 创建 `backend/.env`，不要覆盖已有凭据。

| 配置文件            | 变量                       | 用途                                                      |
| ------------------- | -------------------------- | --------------------------------------------------------- |
| frontend/.env.local | VITE_API_BASE_URL          | FastAPI地址，默认http://localhost:8000/api/v1             |
| frontend/.env.local | VITE_AMAP_KEY              | 高德Web端JS API Key                                       |
| frontend/.env.local | VITE_AMAP_SECURITY_JS_CODE | JS安全码；也可配置VITE_AMAP_SECURITY_SERVICE_HOST安全代理 |
| backend/.env        | DATABASE_URL               | MySQL连接；密码特殊字符须URL编码                          |
| backend/.env        | AMAP_WEBSERVICE_KEY        | 高德Web服务Key，仅后端保存                                |
| backend/.env        | CORS_ORIGINS               | 允许访问后端的前端域名JSON数组                            |

所有VITE变量会进入浏览器；禁止写入数据库密码或Web服务Key。示例文件仅提供空值或占位密码。真实数据库、环境、采集断点与分析结果不随Git发布；新机器须配置数据库并恢复授权的数据备份，不能仅靠克隆恢复真实数据。

## 启动

本机目录 `R:\ev-charging-analysis`。三个PowerShell终端分别运行：

```powershell
.\scripts\start-mysql.ps1
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

MySQL脚本只启动已有 `backend/.runtime/mysql`，默认23306端口；安装路径用MYSQL_SERVER_HOME或-ServerHome设置。使用系统MySQL服务时跳过该脚本，按实际端口配置DATABASE_URL。

前端也可在根目录运行 `npm.cmd run dev`，默认5173；后端在backend工作目录运行 `.\.conda\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。PyCharm打开根目录，解释器选backend/.conda/python.exe，后端工作目录为backend。首次部署数据库操作见[后端说明](backend/README.md)，现有数据库禁止自动初始化或降级。

## 构建与部署

```powershell
npm.cmd run build
```

产物为frontend/dist。配置Vue history回退与/api反向代理；生产使用进程管理器启动FastAPI，不使用Vite开发服务器发布。[部署指南](docs/guides/DEPLOYMENT.md)提供配置示例。开发格式工具：npm.cmd run format、npm.cmd run format:check；Python开发工具通过requirements-dev.txt安装。

## 数据与维护边界

保留真实POI采集分页、限速、重试、断点，质量复核、空间快照和道路OD缓存。道路采样会消耗高德额度，启动新任务前估算请求量并确认配额。当前不提供供需、选址、容量、排队或AI业务。历史选址表与迁移保留，不提供对应业务API；不执行破坏性迁移。

本交付按要求删除自动化测试体系，本轮未运行自动化测试、构建或浏览器功能验证，不能据此宣称功能已验证。工程整理范围与逐文件删除记录见[整理清单](docs/guides/PROJECT_CLEANUP.md)。

[文档索引](docs/README.md) · [分析方法](docs/guides/SPATIAL_METHODS.md) · [道路口径](docs/guides/ROAD_ACCESSIBILITY.md) · [真实采集](docs/guides/COLLECTOR.md)
