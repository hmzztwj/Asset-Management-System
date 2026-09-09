@echo off
chcp 65001 >nul
title 导入/同步实际资产数据
echo ============================================
echo  资产数据导入/同步工具
echo ============================================
echo  运行本脚本会按财务编码同步「实际数据」中的资产台账，
echo  默认不会清空已有的领用/变更记录，可放心重复执行。
echo.
cd /d "%~dp0"
python import_real_data.py
echo.
echo 如需完整重建（会清空 领用/变更/资产/部门 后重新导入）：
echo   python import_real_data.py --reset
echo.
pause
