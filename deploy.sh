#!/bin/bash
set -e

DEPLOY_DIR="/home/alex/homelabdashboard"

echo "[deploy] Pulling latest from GitHub..."
cd "$DEPLOY_DIR"
git pull origin main

echo "[deploy] Installing/updating Python dependencies..."
"$DEPLOY_DIR/venv/bin/pip" install -q -r requirements.txt

echo "[deploy] Restarting service..."
sudo systemctl restart homelabdashboard

echo "[deploy] Status:"
sleep 2
sudo systemctl status homelabdashboard --no-pager -l

echo "[deploy] Done."
