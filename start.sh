#!/bin/bash

# Project Management Dashboard - Quick Start Script

echo "🚀 Starting Project Management Dashboard..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python is installed"

# Check if pip is installed
if ! command -v pip &> /dev/null; then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

echo "✅ pip is installed"

# Install requirements
echo ""
echo "📦 Installing required packages..."
pip install -r requirements.txt

# Check if installation was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All packages installed successfully!"
    echo ""
    echo "🎯 Launching the dashboard..."
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Dashboard will open in your browser at:"
    echo "🌐 http://localhost:8501"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    
    # Run the application
    streamlit run app.py
else
    echo ""
    echo "❌ Failed to install packages. Please check the error messages above."
    exit 1
fi
