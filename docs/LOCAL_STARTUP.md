# 本机启动与目录迁移

当前主项目目录：`R:\ev-charging-analysis`。PyCharm 打开该根目录，Python 解释器选择 `R:\ev-charging-analysis\backend\.conda\python.exe`。

## 工程分层

保留已有 Vite 根目录布局，避免修改导入路径和构建入口：

- `src/`：前端页面、组件、状态、API、地图配置与样式。
- `public/`：前端静态资源；`tests/frontend/`：前端测试。
- `backend/app/`：FastAPI API、模型、Schema、采集与分析服务。
- `backend/alembic/`：数据库迁移；`backend/tests/`：隔离数据库测试。
- `scripts/`：开发、检查与本机启动脚本；`docs/`：方法、接口与验收记录。
- 根目录保留 Vite、npm、格式及环境变量模板，后端依赖配置独立放在 `backend/`。

不提交 `.env.local`、`backend/.env`、`backend/.conda/`、`backend/.runtime/`、`node_modules/`、`dist/`、IDE 和助手本地资料。实际数据库只在本机保留；远程仓库中的数据摘要不替代 MySQL 数据备份。

## 当前电脑启动

在三个 PowerShell 终端分别运行（保持终端运行）：

```powershell
cd R:\ev-charging-analysis
.\scripts\start-mysql.ps1
```

```powershell
cd R:\ev-charging-analysis
.\scripts\start-backend.ps1
```

```powershell
cd R:\ev-charging-analysis
.\scripts\start-frontend.ps1
```

MySQL 脚本只启动已存在的本机数据目录，不初始化、不删除数据。端口已监听时不会重复启动。MySQL 安装位置不同时使用 `-ServerHome` 参数或 `MYSQL_SERVER_HOME` 环境变量。后端端口 8000，前端通常 5173（以 Vite 输出为准）。如果本机执行策略阻止脚本，可按 README 直接运行对应 Python/npm/mysqld 命令，无需修改系统执行策略。

在 PyCharm 添加 Python 运行配置：模块 `uvicorn`，参数 `app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log`，工作目录 `R:\ev-charging-analysis\backend`。MySQL 仍须先启动；前端在 PyCharm Terminal 运行 `npm.cmd run dev`。

## 新电脑安装

```powershell
cd R:\ev-charging-analysis
npm.cmd ci
cd backend
conda env create --prefix .\.conda --file environment.yml
conda activate .\.conda
```

只在配置文件不存在时从 `.env.example` 建立自己的配置；不要覆盖已有 Key。按后端 README 创建并配置自己的 MySQL 库，然后执行 `python -m alembic upgrade head`、`python -m app.db.import_regions`。Git 克隆不携带本机真实数据库；需要独立、安全地恢复数据库备份后才会显示原有真实站点。
