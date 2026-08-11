@echo off
chcp 65001 >nul 2>&1
title GARGI - Build
echo.
echo   GARGI executable builder
echo.

set PY=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo   Python not found
        pause
        exit /b 1
    )
    set PY=py
)

echo   1. PyInstaller  (fast)
echo   2. Nuitka       (slower, fewer AV flags)
echo.
set /p METHOD="   Choose (1/2): "

if "%METHOD%"=="" set METHOD=1
if "%METHOD%"=="1" set FLAG=pyinstaller
if "%METHOD%"=="2" set FLAG=nuitka

echo.
%PY% "%~dp0build.py" %FLAG%

echo.
pause
