#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installing Mediapipe dependencies for Raspberry Pi...${NC}"

# Check if running on Raspberry Pi and architecture
ARCH=$(uname -m)
if ! grep -q "Raspberry Pi" /proc/cpuinfo && \
   ! grep -q "raspberrypi" /proc/device-tree/model 2>/dev/null; then
    echo -e "${RED}This script is intended for Raspberry Pi only.${NC}"
    exit 1
fi

echo -e "${YELLOW}Detected architecture: ${ARCH}${NC}"
if [[ "$ARCH" != "aarch64" ]]; then
    echo -e "${RED}This script requires 64-bit Raspberry Pi OS.${NC}"
    exit 1
fi

# Clean up previous installation
echo -e "${YELLOW}Cleaning up previous installation...${NC}"
if [ -d "venv" ]; then
    rm -rf venv
fi

# Install system dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
sudo apt-get update
sudo apt-get install -y \
    python3-dev \
    cmake \
    protobuf-compiler \
    build-essential \
    pkg-config \
    libatlas-base-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libxvidcore-dev \
    libx264-dev \
    libtbbmalloc2 \
    libtbb-dev \
    libdc1394-25 \
    libv4l-dev \
    libopenblas-dev \
    libhdf5-dev \
    libprotobuf-dev \
    libgoogle-glog-dev \
    python3-pip \
    python3-venv \
    wget \
    build-essential \
    zlib1g-dev \
    libncurses5-dev \
    libgdbm-dev \
    libnss3-dev \
    libssl-dev \
    libreadline-dev \
    libffi-dev \
    libsqlite3-dev \
    libbz2-dev

# Install Python 3.10 if not present
echo -e "${YELLOW}Installing Python 3.10...${NC}"
if ! command -v python3.10 &> /dev/null; then
    PYTHON_VERSION="3.10.13"
    PYTHON_DIR="Python-${PYTHON_VERSION}"
    
    # Download and extract Python source
    wget https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_DIR}.tgz
    tar -xf ${PYTHON_DIR}.tgz
    
    # Build Python with proper permissions
    cd ${PYTHON_DIR}
    ./configure --enable-optimizations
    make -j$(nproc)
    
    # Install Python system-wide
    sudo make altinstall
    
    # Clean up with proper permissions
    cd ..
    # Change ownership of build files before removal
    sudo chown -R $USER:$USER ${PYTHON_DIR}
    rm -rf ${PYTHON_DIR}
    rm -f ${PYTHON_DIR}.tgz
fi

# Create and activate virtual environment with Python 3.10
echo -e "${YELLOW}Creating fresh virtual environment with Python 3.10...${NC}"
python3.10 -m venv venv
source venv/bin/activate

# Verify Python version
PYTHON_VERSION=$(python --version)
if [[ ! $PYTHON_VERSION == *"3.10"* ]]; then
    echo -e "${RED}Wrong Python version in virtual environment. Got ${PYTHON_VERSION}, expected Python 3.10.x${NC}"
    exit 1
fi

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
python -m pip install --upgrade pip wheel setuptools

# Install core dependencies first
pip install 'numpy<2.0.0'
pip install 'protobuf<5.0.0'
pip install opencv-contrib-python

# Install mediapipe
echo -e "${YELLOW}Installing mediapipe...${NC}"
pip install mediapipe

# Install project dependencies
echo -e "${YELLOW}Installing project dependencies...${NC}"
pip install websockets
pip install asyncio
pip install aiohttp
pip install python-socketio
pip install flask
pip install flask-socketio
pip install pillow
pip install imutils

echo -e "${GREEN}Dependencies installation complete!${NC}"

# Test the installation
echo -e "${YELLOW}Testing mediapipe installation...${NC}"
python -c "import mediapipe as mp; print(f'Mediapipe version: {mp.__version__}')"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Mediapipe installed successfully!${NC}"
else
    echo -e "${RED}Mediapipe installation test failed. Please check the error messages above.${NC}"
fi 