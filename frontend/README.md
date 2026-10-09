# 前端工程

Vue 3 + JavaScript + Vite，包含四个正式专题和市州详情。源码按views、components、api、stores、router、config、utils、styles分层；地图组件位于components/maps，真实GIS资源位于assets。

```powershell
cd R:\ev-charging-analysis\frontend
npm.cmd ci
npm.cmd run dev
```

仅在文件不存在时将.env.example复制为.env.local，填写VITE_API_BASE_URL、VITE_AMAP_KEY和JS安全配置。后端密钥禁止写入VITE变量。真实站点只读取FastAPI，不提供模拟回退。

构建命令npm.cmd run build，产物dist；格式命令npm.cmd run format。根目录提供相应命令转发。部署配置history回退，详见[部署指南](../docs/guides/DEPLOYMENT.md)。

自动化测试体系已按交付要求移除，本轮未运行测试或功能验证。
