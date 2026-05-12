#!/bin/bash
# ACL Rehab Coach Start Script

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n🛑 Stopping services..."
    if [ -n "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null
    fi
    exit 0
}

# Set up the trap for SIGINT and SIGTERM (Ctrl+C)
trap cleanup SIGINT SIGTERM

echo "🚀 Starting Python FastAPI backend..."
source .venv/bin/activate
npm run python:start &
BACKEND_PID=$!

echo "⏳ Waiting a few seconds for backend to initialize..."
sleep 3

echo "📱 Starting Node.js WhatsApp bridge..."
echo "Note: You will need to scan the QR code in this terminal if not already authenticated."
npm run start:bridge

# Wait for background processes to finish (if bridge exits, we cleanup)
cleanup
