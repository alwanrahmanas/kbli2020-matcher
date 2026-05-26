@echo off
echo Starting KBLI 2020 Code Lookup Backend with AUTO-RELOAD...
echo.
echo ⚡ Backend will automatically restart when you save changes
echo Press Ctrl+C to stop
echo.
cd /d "%~dp0backend"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python tidak ditemukan. Install Python 3.11+ lalu jalankan ulang script ini.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)
%PYTHON_CMD% -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
