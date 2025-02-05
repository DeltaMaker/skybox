#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up Python environment for Skylight...${NC}"

# Check for Python 3.10
if command -v python3.10 >/dev/null 2>&1; then
    PYTHON_CMD=python3.10
else
    echo "Python 3.10 is required but not found. Please install Python 3.10"
    echo "On Ubuntu/Debian: sudo apt install python3.10 python3.10-venv"
    echo "On macOS: brew install python@3.10"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python 3.10 virtual environment...${NC}"
    $PYTHON_CMD -m venv --system-site-packages venv
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
    # Check if it's Python 3.10
    VENV_PYTHON_VERSION=$(./venv/bin/python --version)
    if [[ $VENV_PYTHON_VERSION != *"3.10"* ]]; then
        echo -e "${YELLOW}Existing environment is not Python 3.10. Recreating...${NC}"
        rm -rf venv
        $PYTHON_CMD -m venv --system-site-packages venv
    fi
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Verify Python version
ACTIVE_PYTHON_VERSION=$(python --version)
echo -e "${YELLOW}Using ${ACTIVE_PYTHON_VERSION}${NC}"

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
python -m pip install --upgrade pip

# Install core dependencies
echo -e "${YELLOW}Installing core dependencies...${NC}"
pip install aiohttp \
    websockets \
    opencv-contrib-python \
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
