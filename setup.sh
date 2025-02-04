#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up Python environment for Skylight...${NC}"

# Check Python version
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
else
    echo "Python 3 is required but not found. Please install Python 3."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv venv
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
python -m pip install --upgrade pip

# Install core dependencies
echo -e "${YELLOW}Installing core dependencies...${NC}"
pip install aiohttp \
    websockets \
    pytest \
    pytest-asyncio

# Check if we're on Raspberry Pi
if [[ $(uname -m) == "arm"* ]] && [[ -f "/etc/rpi-issue" ]]; then
    echo -e "${YELLOW}Installing Raspberry Pi specific dependencies...${NC}"
    pip install rpi.gpio \
        adafruit-circuitpython-neopixel
fi

# Check if we're on macOS and install development dependencies
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}Installing macOS development dependencies...${NC}"
    pip install mock
fi

# Create requirements.txt
echo -e "${YELLOW}Generating requirements.txt...${NC}"
pip freeze > requirements.txt

echo -e "${GREEN}Setup complete! To activate the environment:${NC}"
echo -e "${YELLOW}source venv/bin/activate${NC}" 
