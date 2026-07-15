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
        echo "FastAPI server is already running with PID $PID."
        exit 0
    fi
    rm backend/server.pid
fi

# Start uvicorn in the background from the backend directory
cd backend
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > uvicorn.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > server.pid

echo "Server started successfully!"
echo "- Process ID: $SERVER_PID"
echo "- Log file: backend/uvicorn.log"
echo "- Swagger UI: http://localhost:8000/docs"
echo "- Redoc: http://localhost:8000/redoc"
