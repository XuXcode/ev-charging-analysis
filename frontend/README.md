# 前端工程

Vue 3 + JavaScript + Vite，包含四个正式分析页和市州详情。源码按views、components、api、stores、router、config、utils、styles分层；地图组件位于components/maps，真实GIS资源位于assets。

```powershell
cd R:\ev-charging-analysis\frontend
npm.cmd ci
npm.cmd run dev
```

仅在文件不存在时将.env.example复制为.env.local，填写VITE_API_BASE_URL、VITE_AMAP_KEY和JS安全配置。后端密钥禁止写入VITE变量。真实站点只读取FastAPI。部分总览指标可显式启用既有导出快照回放，默认关闭；不提供离线站点或未计算的分析结果。

构建命令npm.cmd run build，产物dist；格式命令npm.cmd run format。根目录提供相应命令转发。部署配置history回退，详见[部署指南](../docs/guides/DEPLOYMENT.md)。

## 地图交互

全省专题地图和空间分析地图支持左键拖动、滚轮缩放及悬停联动；市州/区县高德地图支持站点、聚合、热力和边界图层。站点弹窗将来源、坐标和质量批次折叠为详情，保留样本完整性提醒。

正式路由：`/`、`/analysis/spatial`、`/analysis/accessibility`、`/analysis/differences`；市州详情为 `/city/:cityCode`。

省级GeoJSON地图不需要高德JS Key；高德实景地图需要Key与安全配置。前端环境变量在启动/构建时读取，修改后需要重启开发服务器或重新构建。API默认指向 `http://localhost:8000/api/v1`；更换后端端口须同步修改。

仓库不包含自动化测试套件。构建、格式检查与浏览器功能核验应分别说明结果，不能互相替代。

全部页面统一使用MonitorLayout玻璃悬浮框架。总览/空间/市州以真实地图为画布，可达性保留独立道路指标与清单，市州差异以图表为主。左右面板可折叠，顶部“纯地图”隐藏面板，Esc恢复；筛选条件和侧栏偏好保留，主题地图与市州地图支持视角记忆。LOCA作为附加SDK加载，失败不会阻断市州普通底图。离线回放仅在 `VITE_DEMO_FALLBACK=auto` 时启用，界面注明非实时；生产配置保持 `off`。

玻璃变量集中在 `src/config/design-tokens.json`，通过根目录 `npm.cmd run tokens` 生成tokens.css；浮层、安全区与响应式规则在 `src/styles/monitor.css`。地图安全区由 `utils/map-viewport.js` 管理，避免折叠面板时重复创建地图。
