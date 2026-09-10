@echo off
chcp 65001 >nul
title 转换固定资产表为导入模板
cd /d "%~dp0"
echo 正在把 实际数据\迈德固定资产在线表.xlsx 转换为页面导入模板...
echo （加参数可调整，例如 --fill-user / --create-departments）
echo.
python convert_to_template.py %*
echo.
pause
