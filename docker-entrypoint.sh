#!/bin/sh
# ---- 容器启动脚本：迁移 → 收集静态文件 → 初始化内置账号 → 启动服务 ----
set -e

echo "[entrypoint] 应用数据库迁移..."
python manage.py migrate --noinput

echo "[entrypoint] 收集静态文件..."
python manage.py collectstatic --noinput

echo "[entrypoint] 确保内置管理员账号存在..."
python ensure_admin.py

echo "[entrypoint] 启动 gunicorn（单进程多线程：密码锁定计数依赖进程内存）..."
exec gunicorn assets_system.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
