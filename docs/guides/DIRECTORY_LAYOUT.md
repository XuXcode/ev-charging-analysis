# 工程目录

完整目录树见根README。frontend按views/components/api/stores/router/config/utils/assets/styles分层；backend按api/services/repositories/schemas/models/db/core/utils分层，保持既有业务关系。

真实行政区导入文件位于backend/app/db/data/regions.json。前后端共同使用的GIS边界和分类规则仍位于frontend/src/assets、frontend/src/config，后端路径已统一指向frontend。

保留Alembic迁移链、真实资源、质量证据和采集记录。backend/.runtime内数据库、分析、边界与采集目录不改动；用途不明确的历史证据保留并排除Git。删除测试、模拟种子、构建产物、确定可重建的缓存和过期开发文档。

Node依赖及Conda环境为本地运行所需，保留但忽略。运行依赖与开发格式工具分开，项目不再提供自动化测试命令。
