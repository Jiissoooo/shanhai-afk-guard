@echo off
rem Æô¶¯.bat - double click this
rem Auto-elevates because game platform processes run at High integrity.
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

rem --- Admin check via integrity level ---
rem Do NOT use "net session" or "fltmc": both return 0 even in a Medium
rem integrity shell (verified on this machine), so they silently skip UAC
rem and the tool then cannot touch High integrity game processes.
whoami /groups 2>nul | findstr /I /C:"Mandatory Label\\High" /C:"Mandatory Label\\System" >nul
if not errorlevel 1 goto :run

echo [*] Administrator rights required.
echo     Game platform processes (wegame/SEGameTool/game exe) run at High
echo     integrity. Without elevation Windows UIPI blocks the key injection
echo     and PostMessage returns err=5 ACCESS_DENIED.
echo.
echo [*] Requesting elevation - click "Yes" on the UAC prompt...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0'"
if errorlevel 1 (
  echo.
  echo [x] Elevation failed. Right click this file -^> "Run as administrator".
  pause
)
exit /b

:run
echo [*] Elevated. Starting...
call "%~dp0scripts\find_python.bat"
if not defined PYEXE goto :nopython
echo [*] Interpreter: %PYEXE%
"%PYEXE%" "%~dp0main.py" %*
if errorlevel 1 (
  echo.
  echo [x] Start failed, exit code %errorlevel%
  pause
)
exit /b 0

:nopython
echo.
echo [x] No usable Python found.
echo     Install Python 3.10+ and tick "Add python.exe to PATH":
echo     https://www.python.org/downloads/windows/
echo     The 0-byte Microsoft Store stub does not count.
pause
exit /b 1