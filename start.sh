#!/bin/bash

# Pinellas True Flood Risk - Startup Script
# Works on Linux and macOS
#
# Usage:
#   ./start.sh          # Quick start (instant, uses demo data)
#   ./start.sh --full   # Download real NOAA historical data

echo "============================================================"
echo "    PINELLAS TRUE FLOOD RISK ASSESSMENT TOOL"
echo "============================================================"
echo ""

# Check for --full flag
export QUICK_START=1
if [ "$1" == "--full" ] || [ "$1" == "-f" ]; then
    export QUICK_START=0
fi

# Navigate to script directory
cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.10+ first"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed"
    echo "Please install Node.js from https://nodejs.org"
    exit 1
fi

# Create/activate Python virtual environment
if [ ! -d "backend/venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv backend/venv
fi

echo "Activating virtual environment..."
source backend/venv/bin/activate

# Install Python dependencies
echo "Checking Python dependencies..."
pip install -q -r backend/requirements.txt 2>/dev/null

# Install Node dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo ""
    echo "Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
else
    echo "Frontend dependencies already installed."
fi

# Show startup mode
echo ""
if [ "$QUICK_START" == "1" ]; then
    echo "MODE: Quick Start (instant startup with demo calculations)"
    echo "      Run './start.sh --full' to download real NOAA data"
else
    echo "MODE: Full Data (downloading historical data from NOAA)"
    echo "      This may take 5-10 minutes on first run..."
fi
echo ""

# Check if real data exists
if [ -f "backend/data/processed/data_status.json" ]; then
    if grep -q '"is_demo_data": false' "backend/data/processed/data_status.json" 2>/dev/null; then
        echo "Historical data cache found - loading from cache."
        export QUICK_START=0
    fi
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo ""
echo "Starting backend API server..."
cd backend
QUICK_START=$QUICK_START python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for backend (with timeout)
echo "Waiting for API to initialize..."
ATTEMPTS=0
MAX_ATTEMPTS=60

while ! curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ $ATTEMPTS -gt $MAX_ATTEMPTS ]; then
        echo ""
        echo "ERROR: API failed to start after 5 minutes."
        echo "Check for errors above."
        cleanup
        exit 1
    fi
    if [ $ATTEMPTS -gt 12 ]; then
        echo "Still initializing... ($ATTEMPTS/$MAX_ATTEMPTS - downloading NOAA data)"
    else
        echo "Starting..."
    fi
    sleep 5
done
echo "Backend API is ready!"

# Start frontend
echo ""
echo "Starting web interface..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait for frontend
sleep 3

echo ""
echo "============================================================"
echo " APPLICATION READY"
echo "============================================================"
echo ""
echo " Web Interface: http://localhost:3000"
echo " API Docs:      http://127.0.0.1:8000/docs"
echo ""
echo " To download full historical data, visit:"
echo "   http://127.0.0.1:8000/api/v1/data/refresh"
echo ""
echo " Press Ctrl+C to stop."
echo "============================================================"
echo ""

# Open browser (works on Linux and macOS)
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000 2>/dev/null &
elif command -v open &> /dev/null; then
    open http://localhost:3000 &
fi

# Wait for processes
wait
