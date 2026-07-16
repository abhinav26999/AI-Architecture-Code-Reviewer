#!/bin/bash
# Navigate to the root directory
cd "$(dirname "$0")"

echo "=== Starting AI Architecture Reviewer Backend ==="

# Check if virtual environment exists
if [ -f "backend/venv/bin/activate" ]; then
    source backend/venv/bin/activate
else
    echo "Error: Python virtual environment not found at backend/venv."
    echo "Please create it using: python3 -m venv backend/venv && source backend/venv/bin/activate && pip install -r backend/requirements.txt"
    exit 1
fi

# Check if server is already running according to PID file
if [ -f "backend/server.pid" ]; then
    PID=$(cat backend/server.pid)
    if ps -p $PID > /dev/null; then
        echo "FastAPI backend is already running with PID $PID."
        BACKEND_RUNNING=true
    else
        rm backend/server.pid
    fi
fi

if [ "$BACKEND_RUNNING" != true ]; then
    # Start uvicorn in the background from the backend directory
    cd backend
    nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > uvicorn.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > server.pid
    cd ..
    echo "Backend started successfully (PID: $SERVER_PID)!"
fi

# 2. Start Next.js Frontend
echo "--> Starting Frontend (Next.js)..."
if [ -f "frontend/server.pid" ]; then
    PID=$(cat frontend/server.pid)
    if ps -p $PID > /dev/null; then
        echo "Next.js frontend is already running with PID $PID."
        FRONTEND_RUNNING=true
    else
        rm frontend/server.pid
    fi
fi

if [ "$FRONTEND_RUNNING" != true ]; then
    cd frontend
    nohup npm run dev > next_dev.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > server.pid
    cd ..
    echo "Frontend started successfully (PID: $FRONTEND_PID)!"
fi

echo "======================================================"
echo "All services started successfully!"
echo "- Backend API: http://127.0.0.1:8000/docs"
echo "- Frontend Dashboard: http://127.0.0.1:3000"
echo "======================================================"
