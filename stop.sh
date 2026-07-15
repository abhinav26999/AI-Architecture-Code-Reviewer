#!/bin/bash
# Navigate to the root directory
cd "$(dirname "$0")"

echo "=== Stopping AI Architecture Reviewer Backend ==="

# Check if server.pid exists
if [ -f "backend/server.pid" ]; then
    PID=$(cat backend/server.pid)
    echo "Stopping FastAPI server (PID: $PID)..."
    
    kill $PID
    sleep 2
    
    # Check if process is still running
    if ps -p $PID > /dev/null; then
        echo "Server did not shut down. Force killing (SIGKILL)..."
        kill -9 $PID
    fi
    
    rm backend/server.pid
    echo "Server stopped successfully."
else
    # Fallback to check port 8000
    echo "PID file not found. Checking if port 8000 is occupied..."
    PORT_PID=$(lsof -t -i :8000)
    if [ ! -z "$PORT_PID" ]; then
        echo "Found process $PORT_PID running on port 8000. Terminating..."
        kill $PORT_PID
        sleep 1
        echo "Stopped."
    else
        echo "No running server found on port 8000."
    fi
fi
