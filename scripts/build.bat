@echo off
rem ============================================================================
rem  build.bat - build a single-file exe with PyInstaller
rem
rem  Output: dist\ShanhaiAFK.exe  (GUI subsystem, no console, auto-elevates)
rem  Requires: pip install pyinstaller
rem
rem  NOTE: this file is intentionally ASCII-only. .bat is parsed by cmd.exe in
rem  the OEM codepage (936 on zh-CN); UTF-8 Chinese comments would be mangled.
rem ============================================================================
setlocal
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"

rem --- locate python: HELMD_PYTHON > DSH bundled runtime > PATH ---
set "PYEXE="
if defined HELMD_PYTHON set "PYEXE=%HELMD_PYTHON%"
if not defined PYEXE if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
    set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
)
if not defined PYEXE (
    echo [x] Python not found. Install Python 3.10+ or set HELMD_PYTHON.
    exit /b 1
)
echo [*] interpreter: %PYEXE%

echo [*] checking PyInstaller...
"%PYEXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [!] not installed, installing...
    "%PYEXE%" -m pip install --upgrade pyinstaller
    if errorlevel 1 goto :fail
)

echo [*] building...
"%PYEXE%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "ShanhaiAFK" ^
    --manifest "scripts\app.manifest" ^
    --add-data "assets;assets" ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    --exclude-module PIL ^
    main.py
if errorlevel 1 goto :fail

echo.
echo [+] done: dist\ShanhaiAFK.exe
for %%F in ("dist\ShanhaiAFK.exe") do echo     size: %%~zF bytes
echo.
echo [i] rename launcher output next step:
echo     rename dist\ShanhaiAFK.exe dist\ShanhaiAFK-Controller.exe
goto :eof

:fail
echo.
echo [x] build failed, see errors above
exit /b 1
