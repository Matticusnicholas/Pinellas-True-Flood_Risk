#!/bin/bash

# Pinellas True Flood Risk - Startup Script
# Works on Linux and macOS

set -e

echo "============================================================"
echo "    PINELLAS TRUE FLOOD RISK ASSESSMENT TOOL"
echo "============================================================"
echo ""

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
pip install -q -r backend/requirements.txt

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

# Check for cached data
echo ""
if [ -f "backend/data/processed/data_status.json" ]; then
    echo "Historical data cache found - will load from cache."
else
    echo "============================================================"
    echo " FIRST RUN DETECTED"
    echo "============================================================"
    echo ""
    echo "On first run, the system will download 50 years of"
    echo "historical flood and hurricane data from NOAA."
    echo "This may take 5-10 minutes depending on your connection."
    echo ""
    echo "Data will be cached locally for instant startup next time."
    echo "============================================================"
    echo ""
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
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for backend
echo "Waiting for API to initialize..."
while ! curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; do
    echo "Still initializing... (this may take a few minutes on first run)"
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
echo " Press Ctrl+C to stop."
echo "============================================================"
echo ""

# Open browser (works on Linux and macOS)
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000 &
elif command -v open &> /dev/null; then
    open http://localhost:3000 &
fi

# Wait for processes
wait
