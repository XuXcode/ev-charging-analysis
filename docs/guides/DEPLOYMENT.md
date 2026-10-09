# 部署说明

## 服务与配置

前端为Vite静态构建，后端为FastAPI进程，MySQL独立运行。生产前配置backend/.env的DATABASE_URL、CORS_ORIGINS和Web Service Key；frontend/.env.local或构建环境配置VITE_API_BASE_URL与JS API Key。VITE值为公开客户端配置。

运行npm.cmd run install:frontend、npm.cmd run build，将frontend/dist发布到静态目录。服务端安装backend/requirements.txt（或经部署者确认的锁文件），以backend为工作目录启动python -m uvicorn app.main:app --host 127.0.0.1 --port 8000，由系统服务或进程管理器保持运行。生产不使用--reload。

## Nginx示例

```nginx
server {
    listen 80;
    server_name your-domain.example;
    root /srv/ev-charging-analysis/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

同域部署前端API地址设/api/v1，反向代理保留/api路径。不同域部署填写完整API地址和匹配CORS_ORIGINS；按部署平台配置HTTPS及高德允许访问域名。

## 数据恢复与维护

Git不包含真实MySQL内容、私有凭据、采集检查点和运行快照。迁移仅定义表结构，克隆后必须恢复授权数据备份或显式采集，不能期待空库出现历史结果。完整备份MySQL、采集原始页、边界证据、OD和冻结快照。对已有数据库先审核迁移，禁止自动降级、清库或重建。

本轮只整理工程与配置，没有执行构建、自动化测试或部署验证。上述为部署操作说明，不代表已部署成功。
