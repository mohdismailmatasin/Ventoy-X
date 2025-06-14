#!/bin/bash

# Enhanced Ventoy GUI Launcher with Sudo Session Management
# This script helps manage sudo/pkexec sessions for the GUI

echo "Enhanced Ventoy GUI - Starting with proper permissions..."
echo "============================================================"

# Check if we have the required tools
missing_tools=""

if ! command -v python3 &> /dev/null; then
    missing_tools+="python3 "
fi

if ! command -v pkexec &> /dev/null; then
    missing_tools+="pkexec "
fi

if ! command -v udisksctl &> /dev/null; then
    missing_tools+="udisks2 "
fi

if [ -n "$missing_tools" ]; then
    echo "Error: Missing required tools: $missing_tools"
    echo "Please install them with your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 policykit-1 udisks2"
    echo "  Fedora: sudo dnf install python3 polkit udisks2"
    echo "  Arch: sudo pacman -S python polkit udisks2"
    exit 1
fi

# Check for optional tools
if command -v sbsign &> /dev/null; then
    echo "✓ sbsign found - EFI signing will be available"
else
    echo "! sbsign not found - EFI signing will use Ventoy's built-in certificates"
    echo "  To enable custom EFI signing: sudo apt install sbsigntool"
fi

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Checking dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Starting Enhanced Ventoy GUI..."
echo "✅ Streamlined Operation: Efficient authentication handling!"
echo "   - All installation, mounting, and signing steps are optimized"
echo "   - Minimal interruptions during the process"
echo ""

# Start the application
python main.py

echo "Enhanced Ventoy GUI closed."
