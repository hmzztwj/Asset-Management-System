@echo off
chcp 65001 >nul
title 资产管理系统
echo 正在初始化并启动资产管理系统...
echo （首次运行如需导入实际资产数据，请先执行 import_data.bat）
cd /d "%~dp0"
python manage.py migrate
python ensure_admin.py
start "" "http://127.0.0.1:12036/"
python manage.py runserver 0.0.0.0:12036
pause
