@echo off
title KBLI 2020 Local Backend
echo ========================================
echo   KBLI 2020 - Running Backend Locally
echo ========================================

cd backend
echo [1/2] Installing dependencies...
pip install -r requirements.txt

echo [2/2] Starting Backend Server...
echo.
python main.py

pause
