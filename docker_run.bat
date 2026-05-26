@echo off
echo ========================================
echo   KBLI 2025 - Docker Build and Run
echo ========================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not running!
    echo Please start Docker Desktop first.
    pause
    exit /b 1
)

echo ✅ Docker is running
echo.

REM Build and start containers
echo 🔨 Building Docker image...
docker-compose build

if errorlevel 1 (
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build successful!
echo.

echo 🚀 Starting containers...
docker-compose up -d

if errorlevel 1 (
    echo ❌ Failed to start containers!
    pause
    exit /b 1
)

echo.
echo ✅ Containers started successfully!
echo.

REM Get local IP address
echo 🌐 Finding your network IP address...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set IP=%%a
    goto :found
)

:found
REM Remove leading space
set IP=%IP:~1%

echo.
echo ========================================
echo   🎉 Application is running!
echo ========================================
echo.
echo Access from this computer:
echo   👉 http://localhost:3001/app
echo.
echo Access from other devices on the same network:
echo   👉 http://%IP%:3001/app
echo.
echo ========================================
echo.
echo To stop the application, run: docker-compose down
echo To view logs, run: docker-compose logs -f
echo.

REM Open browser
echo Opening browser...
timeout /t 2 /nobreak >nul
start http://localhost:3001/app

pause
