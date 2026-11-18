@echo off
rem run_admin.bat - 以管理员身份启动（推荐）
rem 游戏平台(WeGame/TASLogin/游戏本体)常以管理员运行 = High 完整性，
rem 普通权限的工具向它发消息会被 UIPI 拦截(ERROR_ACCESS_DENIED=5)。
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
    echo [*] 正在请求管理员权限...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)
set PYTHONIOENCODING=utf-8
python main.py
if errorlevel 1 (
    echo.
    echo [x] 启动失败。请确认已安装 Python 3.10+ 并已加入 PATH。
    pause
)
