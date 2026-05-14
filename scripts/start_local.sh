#!/usr/bin/env bash
# Jholey Doctor — Local network startup script
# Starts backend + webapp in LAN mode (no ngrok needed)
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ""
echo "🩺 Jholey Doctor — Local Network Mode"
echo "======================================"

# Check Ollama
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "⚠  Ollama not running. Please start the Ollama app first."
  exit 1
fi
echo "✅ Ollama running"

# Warm up model
echo "🔥 Warming up Gemma 4..."
curl -s -X POST http://localhost:11434/api/generate \
  -d '{"model":"gemma4:e4b","prompt":"hi","stream":false,"keep_alive":"30m","options":{"num_predict":1}}' > /dev/null
echo "✅ Model ready"

# Start backend
echo "🚀 Starting backend (port 8000)..."
cd "$ROOT/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 2
echo "✅ Backend running (PID $BACKEND_PID)"

# Start webapp
echo "🚀 Starting webapp (port 8501)..."
cd "$ROOT/webapp"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8501 &
WEBAPP_PID=$!
sleep 3

# Get LAN IP
LAN_IP=$(python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "unknown")

echo ""
echo "======================================"
echo "✅ Jholey Doctor is running!"
echo ""
echo "  Local:   http://localhost:8501"
echo "  Network: http://$LAN_IP:8501"
echo "  Dashboard: http://$LAN_IP:8000/dashboard"
echo ""
echo "Share the Network URL with field devices on the same WiFi."
echo "Press Ctrl+C to stop all services."
echo "======================================"

# Wait and cleanup on exit
trap "kill $BACKEND_PID $WEBAPP_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
