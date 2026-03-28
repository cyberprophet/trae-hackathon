#!/usr/bin/env bash
set -euo pipefail

HOST="116.32.205.3"
USER="jim"
PORT="31222"
REMOTE_PATH="/home/jim/trae-hackathon"
SSH="ssh -p $PORT $USER@$HOST"

echo "=== ShotCraft Backend Deploy ==="

# 1. Sync backend files
echo "[1/3] Syncing files..."
rsync -avz --delete \
  -e "ssh -p $PORT" \
  --exclude '.env' \
  --exclude 'output/' \
  --exclude '__pycache__/' \
  --exclude '.adk/' \
  --exclude '.venv/' \
  backend/ \
  "${USER}@${HOST}:${REMOTE_PATH}/backend/"

# 2. Install deps with venv
echo "[2/3] Installing dependencies..."
$SSH << 'REMOTE'
set -euo pipefail
cd /home/jim/trae-hackathon/backend

# Create venv if not exists
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/pip install --no-cache-dir -r requirements.txt
mkdir -p output
REMOTE

# 3. Restart service
echo "[3/3] Restarting service..."
$SSH << 'REMOTE'
set -euo pipefail

# Kill existing process on port 8000
PID=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$PID" ]; then
  kill $PID 2>/dev/null || true
  sleep 1
fi

cd /home/jim/trae-hackathon/backend
nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/shotcraft.log 2>&1 &
sleep 2

# Verify
if curl -s http://localhost:8000/health | grep -q '"ok"'; then
  echo "✓ Backend running on :8000"
else
  echo "✗ Failed to start. Check /tmp/shotcraft.log"
  tail -20 /tmp/shotcraft.log
  exit 1
fi
REMOTE

echo "=== Deploy complete ==="
