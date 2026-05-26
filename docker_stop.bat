@echo off
echo ========================================
echo   KBLI 2025 - Stop Docker Containers
echo ========================================
echo.

docker-compose down

echo.
echo ✅ Containers stopped and removed
echo.
pause
