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

# --- Dependency bootstrap ---------------------------------------------------
for CMD in python3 node npm; do
    if ! command -v $CMD >/dev/null 2>&1; then
        echo -e "${RED}Missing '$CMD'. On Arch/CachyOS: sudo pacman -S python nodejs npm${NC}"
        exit 1
    fi
done

PYTHON_BIN="./venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo -e "${YELLOW}No venv found — creating one${NC}"
    python3 -m venv venv || { echo -e "${RED}venv creation failed${NC}"; exit 1; }
fi

# Install/refresh Python deps whenever requirements.txt changes or core imports fail
REQ_STAMP="venv/.requirements.sha"
REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ "$(cat "$REQ_STAMP" 2>/dev/null)" != "$REQ_HASH" ] || \
   ! $PYTHON_BIN -c "import fastapi, uvicorn, multipart, PIL, platformdirs, pyparsing" >/dev/null 2>&1; then
    echo -e "${YELLOW}Installing Python dependencies${NC}"
    if ! $PYTHON_BIN -m pip install -r requirements.txt; then
        # Optional packages (cv2/datasets) may lack wheels for new Python versions;
        # fall back to the required set so the app still starts.
        echo -e "${YELLOW}Full install failed — retrying with core packages only${NC}"
        $PYTHON_BIN -m pip install fastapi "uvicorn[standard]" python-multipart pydantic pillow platformdirs pyparsing numpy \
            || { echo -e "${RED}Python dependency install failed${NC}"; exit 1; }
    fi
    echo "$REQ_HASH" > "$REQ_STAMP"
fi

if [ ! -x frontend/node_modules/.bin/vite ] || [ frontend/package-lock.json -nt frontend/node_modules ]; then
    echo -e "${YELLOW}Installing frontend dependencies${NC}"
    (cd frontend && npm install) || { echo -e "${RED}npm install failed${NC}"; exit 1; }
fi

command -v lsof >/dev/null 2>&1 || echo -e "${YELLOW}lsof not found (sudo pacman -S lsof) — port cleanup skipped${NC}"
command -v zenity >/dev/null 2>&1 || command -v kdialog >/dev/null 2>&1 || \
    echo -e "${YELLOW}No zenity/kdialog — native folder picker unavailable (sudo pacman -S zenity)${NC}"

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
