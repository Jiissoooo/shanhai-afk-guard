@echo off
rem run.bat - 双击即启动
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python main.py
if errorlevel 1 (
    echo.
    echo [x] 启动失败。请确认已安装 Python 3.10+ 并已加入 PATH。
    pause
)
