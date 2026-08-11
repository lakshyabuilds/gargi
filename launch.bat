@echo off
chcp 65001 >nul 2>&1
title GARGI
echo.
echo   Launching GARGI...
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

%PY% -c "import textual, rich, openai" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing dependencies...
    %PY% -m pip install --quiet textual rich openai
)

%PY% "%~dp0gargi.py" %*
pause
