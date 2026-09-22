#!/bin/bash
cd "$(dirname "$0")"

echo "Stopping StockRadar background service..."

if [ -f "data/radar.pid" ]; then
    PID=$(cat "data/radar.pid")
    kill -9 "$PID" 2>/dev/null
    rm -f "data/radar.pid"
fi

# 確保 8765 port 程序關閉
PIDS=$(lsof -ti :8765 2>/dev/null)
if [ -n "$PIDS" ]; then
    kill -9 $PIDS 2>/dev/null
fi

echo "StockRadar service stopped."
