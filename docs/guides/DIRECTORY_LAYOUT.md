# 目录整理说明

前端独立放在 `fortend/`，保留原有组件、路由、依赖版本、真实API和Vue3 + FastAPI + MySQL架构。前端源码、静态资源、测试、检查脚本、Vite配置、npm依赖与锁文件均在此目录。根目录package.json只提供便捷转发，不重复安装依赖；首次安装使用 `npm run install:frontend`。

前端环境文件已原样迁移到 `fortend/.env.local`。后端读取共用分类规则和GeoJSON的位置随目录调整，数据内容和算法保持不变。前端开发服务器只监听前端相关文件，避免扫描MySQL、Conda和pytest临时目录。

文档分类：`guides` 当前指南、`reports` JSON报告、`history` 历史验收与旧截图、`screenshots` 引用截图、`templates` 空模板。旧截图归档保留，不删除采集证据或冻结输入。报告内容保持原样，读取/输出路径已同步到 `docs/reports`。

构建产物和测试/格式缓存可重新生成；真实数据库、Conda、Key、采集断点与原始页保持原位置并继续排除Git。整理后仍须验证前后端测试、质量检查、构建、格式和启动接口。

[历史文档](../history/README.md)中的路径和数量可能对应旧阶段，当前启动以 [启动指南](LOCAL_STARTUP.md)及根README为准。

已删除4个仅含一行说明、未被导入且未注册路由的旧占位文件；真正的空间、道路和选址接口继续保留。

本次验证：后端167项、前端23项测试通过，构建和格式检查通过。密钥检查结果见 [目录整理安全审计](../reports/DIRECTORY_SECURITY_AUDIT.json)。
