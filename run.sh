#!/bin/bash

# AI Business Advisor - Unified Start Script
# This script sets up the environment and runs both frontend and backend.

echo "🚀 Starting AI Business Advisor Setup..."

# 1. Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "Please edit the .env file and add your API keys (NVIDIA_API_KEY, TAVILY_API_KEY)."
fi

# 2. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# 3. Activate and Install Dependencies
echo "🛠️  Updating dependencies..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel > /dev/null
pip install -r requirements.txt > /dev/null

# 4. Start the Application
echo "✅ Setup complete! Application is starting..."
echo "🌐 Once started, open: http://localhost:8000"
echo "------------------------------------------------"

# Run uvicorn - backend serves frontend automatically from /frontend directory
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
