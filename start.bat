@echo off
title Pinellas True Flood Risk
color 0A

echo ============================================================
echo     PINELLAS TRUE FLOOD RISK ASSESSMENT TOOL
echo ============================================================
echo.

:: Navigate to project root
cd /d "%~dp0"

:: Check Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Check Node
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
)

:: Setup Python venv if needed
if not exist "backend\venv" (
    echo Creating Python virtual environment...
    python -m venv backend\venv
)

:: Install Python deps
echo Installing Python dependencies...
call backend\venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt 2>nul

:: Install Node deps if needed
if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

:: Start backend
echo.
echo Starting API server...
start "FloodRiskAPI" /min cmd /c "cd /d "%~dp0backend" && ..\backend\venv\Scripts\activate.bat && python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000"

:: Wait a moment then start frontend
timeout /t 3 /nobreak >nul

echo Starting web interface...
cd frontend
start "FloodRiskWeb" cmd /c "npm run dev"
cd ..

:: Wait for API
echo Waiting for API...
:wait_loop
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>nul
if %ERRORLEVEL% neq 0 goto wait_loop

echo.
echo ============================================================
echo  READY!
echo ============================================================
echo.
echo  Web App:  http://localhost:3000
echo  API:      http://127.0.0.1:8000
echo  API Docs: http://127.0.0.1:8000/docs
echo.
echo  To download historical NOAA data, visit:
echo    http://127.0.0.1:8000/docs#/default/download_data_api_v1_data_download_post
echo.
echo  Press any key to stop all services.
echo ============================================================

:: Open browser
start http://localhost:3000

pause >nul

:: Cleanup
taskkill /FI "WINDOWTITLE eq FloodRiskAPI" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq FloodRiskWeb" /F >nul 2>nul
