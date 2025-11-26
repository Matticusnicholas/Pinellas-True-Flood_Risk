@echo off
title Pinellas True Flood Risk
color 0A

echo ============================================================
echo     PINELLAS TRUE FLOOD RISK ASSESSMENT TOOL
echo ============================================================
echo.

:: Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Check if Node.js is available
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

:: Navigate to project root
cd /d "%~dp0"

:: Check/create Python virtual environment
if not exist "backend\venv" (
    echo Creating Python virtual environment...
    python -m venv backend\venv
)

:: Activate virtual environment and install dependencies
echo.
echo Checking Python dependencies...
call backend\venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt

:: Check/install Node dependencies
if not exist "frontend\node_modules" (
    echo.
    echo Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
) else (
    echo Frontend dependencies already installed.
)

:: Check if data has been initialized
echo.
if exist "backend\data\processed\data_status.json" (
    echo Historical data cache found - will load from cache.
) else (
    echo.
    echo ============================================================
    echo  FIRST RUN DETECTED
    echo ============================================================
    echo.
    echo On first run, the system will download 50 years of
    echo historical flood and hurricane data from NOAA.
    echo This may take 5-10 minutes depending on your connection.
    echo.
    echo Data will be cached locally for instant startup next time.
    echo ============================================================
    echo.
)

:: Start backend server in background
echo.
echo Starting backend API server...
start "Flood Risk API" /min cmd /c "cd /d "%~dp0" && call backend\venv\Scripts\activate.bat && python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --app-dir backend"

:: Wait for backend to start
echo Waiting for API to initialize...
timeout /t 5 /nobreak >nul

:: Check if backend is running
:check_backend
curl -s http://127.0.0.1:8000/health >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Still initializing... (this may take a few minutes on first run)
    timeout /t 5 /nobreak >nul
    goto check_backend
)

echo Backend API is ready!
echo.

:: Start frontend
echo Starting web interface...
cd frontend
start "Flood Risk Frontend" cmd /c "npm run dev"
cd ..

:: Wait for frontend
timeout /t 3 /nobreak >nul

:: Open browser
echo.
echo ============================================================
echo  APPLICATION READY
echo ============================================================
echo.
echo  Web Interface: http://localhost:3000
echo  API Docs:      http://127.0.0.1:8000/docs
echo.
echo  Press Ctrl+C or close this window to stop.
echo ============================================================
echo.

:: Open browser automatically
start http://localhost:3000

:: Keep window open
echo The application is running. Close this window to stop all services.
pause >nul

:: Cleanup - kill background processes
taskkill /FI "WINDOWTITLE eq Flood Risk API" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Flood Risk Frontend" /F >nul 2>nul
