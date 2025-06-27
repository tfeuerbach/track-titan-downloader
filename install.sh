#!/bin/bash

# TrackTitan Downloader Installation Script

echo "TrackTitan Downloader - Installation Script"
echo "============================================"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python version $python_version is too old. Please install Python 3.8 or higher."
    exit 1
fi

echo "✓ Python $python_version found"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    exit 1
fi

echo "✓ pip3 found"

# Install dependencies
echo "Installing dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found"
    if [ -f "env.example" ]; then
        echo "Creating .env file from template..."
        cp env.example .env
        echo "✓ .env file created from template"
        echo "⚠️  Please edit .env file with your TrackTitan credentials"
    else
        echo "❌ env.example not found. Please create a .env file manually."
        exit 1
    fi
else
    echo "✓ .env file found"
fi

# Make main script executable
chmod +x tracktitan_downloader.py

echo ""
echo "🎉 Installation completed!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your TrackTitan credentials"
echo "2. Run: python3 tracktitan_downloader.py"
echo ""
echo "For help: python3 tracktitan_downloader.py --help" 