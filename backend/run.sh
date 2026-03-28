#!/usr/bin/env bash
# Run ShotCraft backend with uv
# Usage: ./run.sh [--reload]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🌀 Starting ShotCraft backend at http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo ""

exec uv run uvicorn main:app --host 0.0.0.0 --port 8000 "${@}"
