#!/bin/bash

# Ventoy-X - Quick Launcher
# Simple launcher that sets up the environment and starts the GUI

# Change to the project root directory
cd "$(dirname "$0")/.."

echo "Ventoy-X - Quick Launcher"
echo "========================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found."
    echo "Please install Python 3 and try again."
    exit 1
fi

# Check if we have required dependencies
if [ ! -f "config/requirements.txt" ]; then
    echo "Error: config/requirements.txt not found."
    exit 1
fi

# Try to create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import PySide6" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q -r config/requirements.txt
else
    echo "Dependencies already installed."
fi

# Launch the application
echo "Starting Ventoy-X..."
python main.py

echo "Ventoy-X closed."
