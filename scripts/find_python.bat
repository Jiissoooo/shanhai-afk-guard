@echo off
rem find_python.bat - locate a real Python interpreter, set PYEXE
setlocal enabledelayedexpansion
set "PYEXE="

if defined HELMD_PYTHON if exist "%HELMD_PYTHON%" set "PYEXE=%HELMD_PYTHON%"

if not defined PYEXE (
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
  ) do (
    if not defined PYEXE if exist %%P set "PYEXE=%%~P"
  )
)

if not defined PYEXE (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PYEXE (
      echo %%I | findstr /I /C:"WindowsApps" >nul
      if errorlevel 1 set "PYEXE=%%I"
    )
  )
)

if not defined PYEXE (
  where py >nul 2>&1
  if not errorlevel 1 set "PYEXE=py"
)

endlocal & set "PYEXE=%PYEXE%" & exit /b 0