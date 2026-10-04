# 迁移验收 · 2026-10-04

主目录已迁移到 `R:\ev-charging-analysis`，保留已有 GitHub 仓库、main 分支、Vue3 + FastAPI + MySQL 架构和目录分层。原 Codex 工作区保留为恢复副本，日常开发应使用新主目录。

- 345 个待提交文件在迁移后与原工作区逐文件 SHA-256 一致（新增本验收文档与行尾规范文件前核验）。
- 本机 `.env.local`、`backend/.env`、私有 MySQL 管理配置按原内容复制，仅留本地；提交文件扫描未匹配本机实际 Key 或数据库密码。
- MySQL 正常关闭后复制，已从目标 `backend/.runtime/mysql` 启动。核验保留 12,601 条 POI、364 条道路缓存、136 份行政边界；需求数据集和优化任务仍为 0，没有伪造结果。
- Conda 使用原项目包缓存离线克隆，实际 `sys.prefix` 为 `R:\ev-charging-analysis\backend\.conda`；`pip check` 无依赖冲突。未直接复制旧解释器前缀。
- 前端使用 `npm ci` 安装锁定依赖；`npm run build`、23 项前端测试、Prettier 检查通过。
- 167 项 pytest、Ruff、Alembic 模型一致性检查通过。旧系统临时目录存在 ACL 限制，完整 pytest 使用目标 `.runtime` 下全新 `--basetemp` 目录执行，未修改系统权限。
- 已从目标目录实际启动 MySQL、FastAPI 和 Vite；前端 5173、后端健康/需求目录/道路结果接口均返回 200。
- 新增三个相对路径启动脚本、EditorConfig 与 Git 行尾规范；忽略 IDE/助手本地资料、密钥、数据库、虚拟环境、依赖和构建产物。

本机启动与 PyCharm 配置见 [启动说明](LOCAL_STARTUP.md)。远程仅保存源码、环境模板、依赖锁定文件、方法与验收材料，不包含本机真实 MySQL 数据目录或 Key。
