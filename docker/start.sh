#!/bin/bash
set -e

echo "🚀 Starting RAPID services..."

# Start FastAPI backend
echo "Starting FastAPI on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 &
FASTAPI_PID=$!

# Wait for FastAPI to be ready
echo "Waiting for FastAPI to be ready..."
sleep 5

# Start Streamlit frontend
echo "Starting Streamlit on port 8501..."
streamlit run app/ui.py --server.port 8501 --server.address 0.0.0.0 --server.headless true &
STREAMLIT_PID=$!

echo "✅ Both services started successfully"
echo "   - FastAPI: http://localhost:8000"
echo "   - Streamlit: http://localhost:8501"

# Handle shutdown gracefully
trap "echo '🛑 Shutting down...'; kill $FASTAPI_PID $STREAMLIT_PID; exit 0" SIGTERM SIGINT

# Wait for both processes
wait
