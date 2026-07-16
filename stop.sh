#!/bin/bash
# Navigate to the root directory
cd "$(dirname "$0")"

echo "=== Stopping AI Architecture Reviewer Application ==="

# 1. Stop Backend
echo "--> Stopping Backend (FastAPI)..."
if [ -f "backend/server.pid" ]; then
    PID=$(cat backend/server.pid)
    echo "Stopping FastAPI backend (PID: $PID)..."
    kill $PID
    sleep 1
    if ps -p $PID > /dev/null; then
        echo "Backend did not shut down. Force killing..."
        kill -9 $PID
    fi
    rm backend/server.pid
    echo "Backend stopped."
else
    PORT_PID=$(lsof -t -i :8000)
    if [ ! -z "$PORT_PID" ]; then
        echo "Found process $PORT_PID running on port 8000. Terminating..."
        kill $PORT_PID
        sleep 1
        echo "Backend stopped."
    else
        echo "No running backend found on port 8000."
    fi
fi

# 2. Stop Frontend
echo "--> Stopping Frontend (Next.js)..."
if [ -f "frontend/server.pid" ]; then
    PID=$(cat frontend/server.pid)
    echo "Stopping Next.js frontend (PID: $PID)..."
    kill $PID
    sleep 1
    if ps -p $PID > /dev/null; then
        echo "Frontend did not shut down. Force killing..."
        kill -9 $PID
    fi
    rm frontend/server.pid
    echo "Frontend stopped."
else
    PORT_PID=$(lsof -t -i :3000)
    if [ ! -z "$PORT_PID" ]; then
        echo "Found process $PORT_PID running on port 3000. Terminating..."
        kill $PORT_PID
        sleep 1
        echo "Frontend stopped."
    else
        echo "No running frontend found on port 3000."
    fi
fi

echo "All services stopped successfully."
