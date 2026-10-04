# 湖南省新能源汽车充电基础设施空间分析与可视化平台

Vue 3 + JavaScript + FastAPI + MySQL。省级专题地图展示14市州空间格局，市州/区县高德地图展示真实入库 POI，专题页提供空间分布、代表点道路观测、低可达性清单及需求与选址基座。

**高德可检索 POI 样本不代表官方设施总量。缺少可靠统计、需求或候选证据时保持待接入，不生成虚构分析结果。**

## 项目目录

```text
ev-charging-analysis/
  fortend/                 前端独立工程（按本项目约定使用此目录名）
    src/                   Vue页面、组件、API、Pinia、路由、配置与地图
    public/                静态文件与公开数据质量快照
    tests/frontend/        前端单元测试
    scripts/               前端fixture、质量与design token检查
    package.json           前端依赖与运行命令
    package-lock.json      前端锁定依赖
    vite.config.js         Vite配置
    .env.example           前端配置模板
  backend/
    app/                   API、领域服务、采集与分析模块
    alembic/               数据库迁移
    tests/                 独立测试数据库用例
    environment.yml        Conda环境定义
    requirements*.txt      Python依赖
  scripts/                 本机启动与跨项目审计工具
  docs/
    guides/                当前开发、接口、方法与启动指南
    reports/               数据质量、性能、采集和复现报告
    history/               历史阶段记录与旧截图
    screenshots/           指南引用的截图
    templates/             空数据导入模板
    data-quality/          人工复核材料
    exports/               保留的演示导出文件
  package.json             根目录快捷命令，转发到fortend
```

后端 Conda、MySQL 数据、采集缓存和本机 Key 均被 Git 忽略。真实数据库不是源码附件，不能通过 Git 克隆恢复；不删除 `backend/.runtime/mysql`、采集检查点或 `.conda` 环境。

## 安装与启动

需要 Node.js 20.19+ 或 22.12+、Conda Python 3.12 与 MySQL 8。本机主目录为 `R:\ev-charging-analysis`。

首次安装前端依赖：

```powershell
cd R:\ev-charging-analysis
npm.cmd run install:frontend
```

仅在配置不存在时，从 `fortend/.env.example` 创建 `fortend/.env.local`，填写前端 JS API Key、安全参数与 API 地址。后端私有配置在 `backend/.env`，准备方式见 [后端说明](backend/README.md)。不要覆盖已有 Key，不把 Web Service Key 或数据库密码放进 Vite 变量。

当前电脑可在三个终端分别运行：

```powershell
.\scripts\start-mysql.ps1
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

也可以在根目录运行 `npm.cmd run dev`，或进入 `fortend` 后运行 `npm.cmd run dev`。前端地址通常为 http://localhost:5173，后端为 http://127.0.0.1:8000；以终端实际输出为准。

PyCharm 打开项目根目录，解释器使用 `backend/.conda/python.exe`，FastAPI 工作目录为 `backend`。详细配置见 [本机启动](docs/guides/LOCAL_STARTUP.md)。

## 验证与构建

在项目根目录执行：

```powershell
npm.cmd run test:frontend
npm.cmd run check
npm.cmd run check:quality
npm.cmd run check:tokens
npm.cmd run build
npm.cmd run format:check
```

前端构建产物为 `fortend/dist/`，部署时为 Vue Router 配置 history 回退。后端验证命令见 `backend/README.md`；测试使用独立 MySQL 测试库，不在真实库导入测试站点。

## 数据与功能边界

默认使用真实 API，失败时显示错误，不回退模拟站点。市州地图提供 Marker、点聚合、POI热力、区县边界、站点检索与视野加载；省级地图使用真实14市州 GeoJSON。

现有122区县道路结果是代表点到候选站的观测，不能解释成人口/面积覆盖。需求与候选模块支持真实数据导入、权重标准化、Greedy/MCLP、调用量估算及冻结输入复现。尚缺真实需求/新建候选数据时不生成推荐方案；缺少桩数、功率与容量时不计算排队。

前端 `src/mock` 中的历史模拟数字仅用于独立fixture检查，专题元信息不含虚构分析结果。真实采集、原始数据、质量判断与统计总量分别管理。

- [文档目录](docs/README.md)
- [目录整理说明](docs/guides/DIRECTORY_LAYOUT.md)
- [接口约定](docs/guides/API_CONTRACT.md)
- [采集链路](docs/guides/COLLECTOR.md)
- [空间方法](docs/guides/SPATIAL_METHODS.md)
- [道路观测](docs/guides/ROAD_ACCESSIBILITY.md)
- [需求与选址](docs/guides/DEMAND_PLANNING.md)

历史阶段的数量、截图与验收结论保存在 `docs/history`，不作为当前数据状态的替代。
