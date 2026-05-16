#!/bin/bash
# =============================================================================
# taxcrawler-dm — Start Script (Mac/Linux)
# =============================================================================
# Usage:
#   ./start.sh          <- starts API server + desktop UI
#   ./start.sh --api    <- starts API server only
#   ./start.sh --cli    <- starts CLI interactive mode
# =============================================================================

set -e

API_HOST="127.0.0.1"
API_PORT="8000"
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo ""
        echo "Stopping server (PID: $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        echo "Server stopped."
    fi
}

trap cleanup EXIT INT TERM

echo ""
echo "============================================="
echo " taxcrawler-dm"
echo "============================================="
echo ""

# -----------------------------------------------------------------------------
# CLI mode
# -----------------------------------------------------------------------------
if [ "$1" == "--cli" ]; then
    echo "Starting CLI interactive mode..."
    python3 cli/main.py
    exit 0
fi

# -----------------------------------------------------------------------------
# Start API server
# -----------------------------------------------------------------------------
echo "Starting API server on http://$API_HOST:$API_PORT ..."
python3 -m uvicorn api.main:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --log-level warning &
SERVER_PID=$!
echo "  Server PID: $SERVER_PID"

# Wait for server to be ready
for i in {1..10}; do
    if curl -s "http://$API_HOST:$API_PORT/health" > /dev/null 2>&1; then
        echo "  Server ready."
        break
    fi
    sleep 1
done
echo ""

# -----------------------------------------------------------------------------
# API only mode
# -----------------------------------------------------------------------------
if [ "$1" == "--api" ]; then
    echo "API running at http://$API_HOST:$API_PORT"
    echo "Docs at http://$API_HOST:$API_PORT/docs"
    echo ""
    echo "Press Ctrl+C to stop."
    wait "$SERVER_PID"
    exit 0
fi

# -----------------------------------------------------------------------------
# Start desktop UI
# -----------------------------------------------------------------------------
echo "Starting desktop UI..."
python3 ui/main.py

echo ""
echo "UI closed."