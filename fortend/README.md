# 前端工程

本目录名按项目约定为 `fortend`，使用 Vue 3、JavaScript、Vite、Ant Design Vue、ECharts、Pinia、Vue Router、Axios 与高德 JS API 2.0。

```powershell
cd R:\ev-charging-analysis\fortend
npm.cmd ci
npm.cmd run dev
```

配置文件位于本目录 `.env.local`，模板为 `.env.example`；已有配置不要覆盖。后端须先启动，API 默认指向8000端口。构建运行 `npm.cmd run build`，产物位于本目录 `dist`。

- `src/views` 页面，`src/components` 复用组件，`src/api` 请求，`src/stores` 状态，`src/config` 配置。
- `public` 静态资源与真实数据质量快照。
- `tests/frontend` 测试，`scripts` 前端检查与设计token生成。
- `src/mock` 历史测试fixture与专题元信息；真实页面不使用模拟业务结果。

根目录 `npm.cmd run dev/build/test:frontend` 命令继续可用，由根 package.json 转发至本工程。

开发与方法文档见 [文档索引](../docs/README.md)，完整启动见 [启动说明](../docs/guides/LOCAL_STARTUP.md)。
