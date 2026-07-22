#!/bin/bash
# Navigate to the root directory
cd "$(dirname "$0")"

echo "=== Stopping AI Architecture Reviewer Application ==="

# 1. Stop Backend
echo "--> Stopping Backend (FastAPI)..."
if [ -f "backend/server.pid" ]; then
    PID=$(cat backend/server.pid)
    echo "Stopping FastAPI backend (PID: $PID)..."
    kill $PID 2>/dev/null || true
    sleep 1
    if ps -p $PID > /dev/null 2>&1; then
        echo "Backend did not shut down. Force killing..."
        kill -9 $PID 2>/dev/null || true
    fi
    rm -f backend/server.pid
fi

# Ensure port 8000 and any uvicorn workers are completely freed
PORT8000_PID=$(lsof -t -i :8000 2>/dev/null)
if [ -n "$PORT8000_PID" ]; then
    echo "Killing remaining process(es) on port 8000: $PORT8000_PID"
    kill -9 $PORT8000_PID 2>/dev/null || true
fi

pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
echo "Backend stopped."

# 2. Stop Celery Worker
echo "--> Stopping Celery Worker..."
if [ -f "backend/celery.pid" ]; then
    PID=$(cat backend/celery.pid)
    echo "Stopping Celery worker (PID: $PID)..."
    kill $PID 2>/dev/null || true
    sleep 1
    if ps -p $PID > /dev/null 2>&1; then
        echo "Celery worker did not shut down. Force killing..."
        kill -9 $PID 2>/dev/null || true
    fi
    rm -f backend/celery.pid
fi

# Ensure all Celery workers are stopped
pkill -9 -f "celery -A app.worker.celery_app" 2>/dev/null || true
echo "Celery worker stopped."

# 3. Stop Frontend
echo "--> Stopping Frontend (Next.js)..."
if [ -f "frontend/server.pid" ]; then
    PID=$(cat frontend/server.pid)
    echo "Stopping Next.js frontend (PID: $PID)..."
    kill $PID 2>/dev/null || true
    sleep 1
    if ps -p $PID > /dev/null 2>&1; then
        echo "Frontend did not shut down. Force killing..."
        kill -9 $PID 2>/dev/null || true
    fi
    rm -f frontend/server.pid
fi

# Ensure port 3000 and any next dev workers are completely freed
PORT3000_PID=$(lsof -t -i :3000 2>/dev/null)
if [ -n "$PORT3000_PID" ]; then
    echo "Killing remaining process(es) on port 3000: $PORT3000_PID"
    kill -9 $PORT3000_PID 2>/dev/null || true
fi

pkill -9 -f "next-dev" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
echo "Frontend stopped."

echo "All services stopped successfully."
