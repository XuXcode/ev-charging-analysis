# 后端与真实接口模式验证

后续真实采集链路已继续开发，当前迁移为 `f233d458f264`、后端64项测试通过。
采集器及配置Key后的真实运行结果见 [COLLECTOR.md](COLLECTOR.md)。
2026-10-03 已实际完成14市州122区县检索，正式库10,745条高德POI，504个页面审计记录。
Web Service和JS Key均通过验证；前端生产构建、Ruff、分页与市州联动通过。
真实库桩数为空，统计快照0条。17区县触及检索上限，入库数量不代表完整设施总量。
以下为最初后端基座阶段的历史验证记录。

验证日期：2026-10-03。本轮保留前端页面结构，新增 backend/，
并根据后续确认加入按市州实时查询高德充电站的入口。

## 已实际执行

| 检查                      | 结果                                                          |
| ------------------------- | ------------------------------------------------------------- |
| Conda 环境                | backend/.conda，Python 3.12.14；已清理未使用的 venv           |
| pip check                 | 无依赖冲突                                                    |
| MySQL                     | 独立 8.4.8 实例，127.0.0.1:23306；已有服务未修改              |
| Alembic upgrade / current | f6d78960c08c，head                                            |
| Alembic check             | No new upgrade operations detected                            |
| 迁移回滚与再升级          | 独立 _test 库执行 downgrade base → upgrade head → check，通过 |
| pytest                    | 38 passed，包含真实 MySQL、HTTP契约与高德适配器测试           |
| Ruff                      | check / format --check 通过                                   |
| FastAPI 启动              | Uvicorn实际启动，/api/health、/docs、/openapi.json可访问      |
| 当前应用数据              | 14市州、0站点、0历史趋势；未知统计为null，simulated=false     |
| npm run build             | 构建成功                                                      |
| 浏览器总览                | 指标空值显示“暂无数据”，无假排名、比例或趋势                  |
| 浏览器市州路由            | 长沙详情、返回全省、区县pending状态通过                       |
| 展示尺寸                  | 1920×1080及普通桌面窗口通过；查询控件不遮挡图层控件           |
| 浏览器错误日志            | 本轮检查未发现error/warn                                      |

截图：[真实接口空统计状态](screenshots/live-mode.png)。

## 高德验证边界

没有提供高德 JS API Key、安全码或后端 Web服务 Key，因此未进行真实高德调用，
也未把静态行政区划图声称为已连通的在线底图。
实际检查了未配置时的提示与禁用状态；后端返回统一503，而不是模拟地点。

适配器通过 MockTransport 校验市州范围、参数、POI字段映射、非法坐标剔除、
分页上限、桩数缺失、超时 / 供应方错误脱敏，并确认查询不写入数据库。
这些测试响应只用于自动化测试，界面不使用它们。
真实连通性与Key权限需配置后验证，详见 [后端README](../backend/README.md)。

## 非阻断提示

当前上游 Starlette TestClient 对 httpx 发出1条弃用提示，测试没有失败。
前端ECharts公共包大于500kB，Vite发出体积提示，构建成功；本轮没有扩大图表依赖。
受沙箱目录读取限制，Vite构建和启动在授权后的环境执行；命令仍为原npm脚本。

应用库 ev_charging_live 只导入行政范围元信息，未导入模拟业务记录。
测试样本在独立测试事务中回滚；先前 ev_charging_demo 不被应用使用。
没有执行真实分析、批量采集或用户权限相关业务。
