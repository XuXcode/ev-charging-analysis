# 后端工程

FastAPI + SQLAlchemy + MySQL。Router负责HTTP契约，Service处理业务，Repository封装查询，Schema定义输入输出，Model维护表映射；采集与空间/道路分析为独立任务，不由读取接口自动触发。

## 环境

推荐Python 3.12。在backend目录：

```powershell
conda env create --prefix .\.conda --file environment.yml
conda activate .\.conda
```

运行依赖在requirements.txt；requirements.lock.txt是既有环境的运行版本参考，本轮未重新验证依赖可安装性。Ruff为可选开发工具，通过requirements-dev.txt安装。HTTPX用于真实高德API，不是测试专用依赖。

仅在不存在时将.env.example复制为.env。配置DATABASE_URL、AMAP_WEBSERVICE_KEY和CORS_ORIGINS；已有私有.env不覆盖。默认.env模板使用3306，本机专用MySQL脚本使用23306，以实际服务为准。

## 数据库与启动

新环境先建立应用库与最低必要权限的用户，恢复授权备份后再启动。以下建库仅供全新部署，不能对已有数据库重复初始化：

```sql
CREATE DATABASE ev_charging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ev_app'@'localhost' IDENTIFIED BY 'replace_me';
GRANT ALL PRIVILEGES ON ev_charging.* TO 'ev_app'@'localhost';
```

全新库准备好凭据后，按需运行alembic upgrade head，再运行python -m app.db.import_regions导入真实行政区元数据；不会导入站点或模拟统计。本轮没有执行迁移。已有库应先备份并审核迁移，禁止downgrade或自动重建。

```powershell
.\.conda\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

本地开发可增加--reload，生产通过进程管理器运行。公开API前缀/api/v1，交互契约/docs，OpenAPI/openapi.json。

## 数据与业务任务

- app/services/collector：真实站点采集、分页、限速、失败重试、断点续跑。
- app/services/analysis：密度、网格、直线覆盖、快照、代表点道路可达性及OD缓存。
- app/services/governance、poi_review、boundary_review：来源、分类、人工复核与边界治理。
- app/services/statistics_import：可靠统计独立导入，不由POI推导桩数或历史趋势。

所有采集和道路计算按[采集说明](../docs/guides/COLLECTOR.md)与[道路方法](../docs/guides/ROAD_ACCESSIBILITY.md)显式运行；新外部请求需要配额确认。保留旧API与历史模型中正式业务仍使用的字段，不因当前页面暂不展示而删除数据库记录。

backend/.runtime保存私有MySQL、采集页、检查点、边界证据、快照和道路结果，不提交Git；backend/.conda也不提交。历史planning_datasets/planning_runs表与Alembic revision链保留，解除业务ORM和API注册；retained_schema过滤器避免自动生成删除这两张表。

本轮已删除测试目录、配置和测试依赖，未执行自动化测试、构建或功能验证。
