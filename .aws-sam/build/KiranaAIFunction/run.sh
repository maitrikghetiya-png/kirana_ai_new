#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check if .venv exists, if not create and install dependencies
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if command -v uv &> /dev/null; then
        uv venv
        uv pip install -r requirements.txt
    else
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt
    fi
fi

echo "=================================================="
echo "🏪 Starting KiranaAI — Udhaar Khata Agent"
echo "🌐 Open in browser: http://localhost:8000"
echo "=================================================="

PYTHON_BIN=".venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

$PYTHON_BIN -m uvicorn backend.handler:app --host 0.0.0.0 --port 8000 --reload
