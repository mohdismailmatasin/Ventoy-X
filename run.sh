#!/bin/bash

# Simple script to run the Ventoy-X GUI application

echo "=== Ventoy-X GUI Application ==="

# Change to the project directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Installing dependencies..."
    venv/bin/pip install -r config/requirements.txt
else
    echo "Virtual environment found."
fi

# Check if PySide6 is installed
if ! venv/bin/python -c "import PySide6" 2>/dev/null; then
    echo "Installing missing dependencies..."
    venv/bin/pip install -r config/requirements.txt
fi

echo "Starting Ventoy-X GUI..."
echo "========================="

# Run the application
venv/bin/python main.py

echo "Application closed."
