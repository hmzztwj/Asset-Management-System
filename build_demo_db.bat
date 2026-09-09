@echo off
chcp 65001 >nul
title 重建演示数据库
echo ============================================
echo  重新生成演示数据库 db.demo.sqlite3
echo  该操作只影响 db.demo.sqlite3，不会改动 db.sqlite3
echo ============================================
cd /d "%~dp0"
set "ASSETS_DB_PATH=%CD%\db.demo.sqlite3"
del /q db.demo.sqlite3 2>nul
python manage.py migrate --noinput
python seed_data.py
python ensure_admin.py
echo.
echo  已重建 db.demo.sqlite3（含演示数据 + 管理员 admin/admin123）
echo.
pause
