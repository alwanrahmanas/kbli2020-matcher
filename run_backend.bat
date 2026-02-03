@echo off
echo Starting KBLI 2020 Code Lookup Backend with AUTO-RELOAD...
echo.
echo ⚡ Backend will automatically restart when you save changes
echo Press Ctrl+C to stop
echo.
cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
