@echo off
title KBLI 2020 Local Backend
echo ========================================
echo   KBLI 2020 - Running Backend Locally
echo ========================================

cd backend
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

echo [1/2] Installing dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt

echo [2/2] Starting Backend Server...
echo.
%PYTHON_CMD% main.py

pause
