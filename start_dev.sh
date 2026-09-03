#!/bin/bash
set -m  # job control: each background job gets its own process group

BACKEND_PORT=8000
FRONTEND_PORT=3000
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE_DIR"

# Parse optional --libraries-root PATH flag
LIBRARIES_ROOT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --libraries-root)
            LIBRARIES_ROOT="$2"
            shift 2
            ;;
        --port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [ -n "$LIBRARIES_ROOT" ]; then
    export TAGGER_LIBRARIES_ROOT="$LIBRARIES_ROOT"
fi

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}Starting Image Tagger dev servers...${NC}"

PYTHON_BIN="./venv/bin/python"
[ ! -f "$PYTHON_BIN" ] && PYTHON_BIN="python3"

# Free ports if already in use
for PORT in $BACKEND_PORT $FRONTEND_PORT; do
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Port $PORT in use — killing existing process${NC}"
        fuser -k $PORT/tcp 2>/dev/null || true
        sleep 1
    fi
done

cleanup() {
    echo -e "\n${RED}Stopping dev servers...${NC}"
    # kill -- -PID sends SIGTERM to the entire process group (set -m above)
    [ -n "$BACKEND_PID"  ] && kill -- -$BACKEND_PID  2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill -- -$FRONTEND_PID 2>/dev/null || true
    wait 2>/dev/null
    exit 0
}
trap cleanup INT TERM

echo -e "${GREEN}Backend  → http://127.0.0.1:$BACKEND_PORT${NC}"
$PYTHON_BIN -m uvicorn src.main:app --port $BACKEND_PORT --reload &
BACKEND_PID=$!

sleep 2

echo -e "${GREEN}Frontend → http://localhost:$FRONTEND_PORT${NC}"
(cd frontend && npm run dev -- --port $FRONTEND_PORT) &
FRONTEND_PID=$!

echo -e "${CYAN}Press Ctrl+C to stop both servers${NC}"
wait
