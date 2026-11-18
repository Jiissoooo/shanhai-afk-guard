@echo off
rem build.bat - 打包成单文件 exe（需要 pip install pyinstaller）
setlocal
cd /d "%~dp0.."
echo [*] 检查 PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [!] 未安装，正在安装...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 goto :fail
)
echo [*] 开始打包...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "山海寻灵防AFK" ^
    --manifest "scripts\app.manifest" ^
    --add-data "app;app" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    main.py
if errorlevel 1 goto :fail
echo.
echo [+] 完成: dist\山海寻灵防AFK.exe
goto :eof

:fail
echo.
echo [x] 打包失败，见上方错误
exit /b 1
