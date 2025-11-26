@echo off
title Pinellas True Flood Risk
color 0A

echo ============================================================
echo     PINELLAS TRUE FLOOD RISK ASSESSMENT TOOL
echo ============================================================
echo.

:: Check for command line argument
set QUICK_START=1
if "%1"=="--full" set QUICK_START=0
if "%1"=="-f" set QUICK_START=0

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
pip install -q -r backend\requirements.txt 2>nul

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

:: Show startup mode
echo.
if "%QUICK_START%"=="1" (
    echo MODE: Quick Start (instant startup with demo calculations)
    echo       Run "start.bat --full" to download real NOAA data
) else (
    echo MODE: Full Data (downloading historical data from NOAA)
    echo       This may take 5-10 minutes on first run...
)
echo.

:: Check if real data exists
if exist "backend\data\processed\data_status.json" (
    findstr /c:"is_demo_data\": false" "backend\data\processed\data_status.json" >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo Historical data cache found - loading from cache.
        set QUICK_START=0
    )
)

:: Start backend server
echo.
echo Starting backend API server...
start "Flood Risk API" /min cmd /c "cd /d "%~dp0" && call backend\venv\Scripts\activate.bat && set QUICK_START=%QUICK_START% && python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --app-dir backend"

:: Wait for backend to start (shorter wait for quick start)
echo Waiting for API to initialize...

if "%QUICK_START%"=="1" (
    timeout /t 3 /nobreak >nul
) else (
    timeout /t 5 /nobreak >nul
)

:: Check if backend is running (with timeout)
set ATTEMPTS=0
:check_backend
set /a ATTEMPTS+=1
curl -s http://127.0.0.1:8000/health >nul 2>nul
if %ERRORLEVEL% neq 0 (
    if %ATTEMPTS% gtr 60 (
        echo.
        echo ERROR: API failed to start after 5 minutes.
        echo Check the "Flood Risk API" window for errors.
        pause
        exit /b 1
    )
    if %ATTEMPTS% gtr 12 (
        echo Still initializing... (%ATTEMPTS%/60 - downloading NOAA data)
    ) else (
        echo Starting...
    )
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
echo  To download full historical data, visit:
echo    http://127.0.0.1:8000/api/v1/data/refresh
echo.
echo  Press any key to stop all services.
echo ============================================================
echo.

:: Open browser automatically
start http://localhost:3000

:: Keep window open
pause >nul

:: Cleanup - kill background processes
echo Shutting down...
taskkill /FI "WINDOWTITLE eq Flood Risk API" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Flood Risk Frontend" /F >nul 2>nul
echo Done.
