# 本机启动

项目：`R:\ev-charging-analysis`。前端：`frontend`；后端：`backend`。

## 当前电脑

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

MySQL 脚本只启动现有 `backend/.runtime/mysql`，不初始化、不删除数据。端口23306已监听时不启动第二份实例。安装位置不同时传 `-ServerHome` 或设置 `MYSQL_SERVER_HOME`。

前端默认5173端口，后端8000。根目录 `npm.cmd run dev` 仍有效；也可进入 `frontend` 执行 `npm.cmd run dev`。配置位置改为 `frontend/.env.local`，后端仍为 `backend/.env`。

## PyCharm

打开项目根目录；解释器选择 `R:\ev-charging-analysis\backend\.conda\python.exe`。

Python运行配置：模块 `uvicorn`；参数 `app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log`；工作目录 `R:\ev-charging-analysis\backend`。先启动 MySQL，前端可在 PyCharm Terminal 运行 `npm.cmd run dev`。

## 新电脑

```powershell
cd R:\ev-charging-analysis
npm.cmd run install:frontend
cd backend
conda env create --prefix .\.conda --file environment.yml
conda activate .\.conda
```

仅在配置不存在时复制模板；前端模板在 `frontend/.env.example`，后端在 `backend/.env.example`。按 [后端说明](../../backend/README.md)配置 MySQL，执行 `python -m alembic upgrade head` 与 `python -m app.db.import_regions`。

远程仓库不包含真实数据库、Key或虚拟环境；原有站点须从独立数据库备份恢复。目录规范与清理范围见 [目录说明](DIRECTORY_LAYOUT.md)。
