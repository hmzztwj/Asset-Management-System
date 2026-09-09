@echo off
chcp 65001 >nul
title 启用演示数据
echo ============================================
echo  启用随仓库分发的演示数据库
echo ============================================
cd /d "%~dp0"

if exist "db.sqlite3" (
    echo.
    echo  已检测到 db.sqlite3，为避免覆盖已有数据，不会替换它。
    echo  若你希望改用演示数据，请手动执行：
    echo      copy /Y db.demo.sqlite3 db.sqlite3
    echo.
) else (
    echo  未检测到 db.sqlite3，将使用演示数据库作为默认库 ...
    copy /Y db.demo.sqlite3 db.sqlite3 >nul
    echo  完成！现在运行 start.bat 即可看到演示数据。
)
echo.
pause
