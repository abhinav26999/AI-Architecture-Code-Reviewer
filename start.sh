#!/bin/bash
# Navigate to the root directory
cd "$(dirname "$0")"

echo "=== Starting AI Architecture Reviewer Application ==="

# Check if virtual environment exists
if [ -f "backend/venv/bin/activate" ]; then
    source backend/venv/bin/activate
else
    echo "Error: Python virtual environment not found at backend/venv."
    echo "Please create it using: python3 -m venv backend/venv && source backend/venv/bin/activate && pip install -r backend/requirements.txt"
    exit 1
fi

# Clean up stale processes on ports 8000 and 3000 before starting
STALE_8000=$(lsof -t -i :8000 2>/dev/null)
if [ -n "$STALE_8000" ]; then
    echo "Cleaning up stale process on port 8000 ($STALE_8000)..."
    kill -9 $STALE_8000 2>/dev/null || true
    rm -f backend/server.pid
fi

STALE_3000=$(lsof -t -i :3000 2>/dev/null)
if [ -n "$STALE_3000" ]; then
    echo "Cleaning up stale process on port 3000 ($STALE_3000)..."
    kill -9 $STALE_3000 2>/dev/null || true
    rm -f frontend/server.pid
fi

# 1. Start FastAPI Backend
echo "--> Starting Backend (FastAPI)..."
cd backend
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > uvicorn.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > server.pid
cd ..
echo "Backend started successfully (PID: $SERVER_PID)!"

# 2. Start Next.js Frontend
echo "--> Starting Frontend (Next.js)..."
cd frontend
nohup npm run dev > next_dev.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > server.pid
cd ..
echo "Frontend started successfully (PID: $FRONTEND_PID)!"

echo "======================================================"
echo "All services started successfully!"
echo "- Backend API: http://127.0.0.1:8000/docs"
echo "- Frontend Dashboard: http://127.0.0.1:3000"
echo "======================================================"
