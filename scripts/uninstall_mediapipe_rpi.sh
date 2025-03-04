#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting cleanup of mediapipe installation...${NC}"

# Deactivate virtual environment if active
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${YELLOW}Deactivating virtual environment...${NC}"
    deactivate
fi

# Remove virtual environment
if [ -d "venv" ]; then
    echo -e "${YELLOW}Removing virtual environment...${NC}"
    rm -rf venv
fi

# Remove pyenv if it exists
if [ -d "$HOME/.pyenv" ]; then
    echo -e "${YELLOW}Removing pyenv...${NC}"
    rm -rf "$HOME/.pyenv"
fi

# Remove pyenv from shell configuration
echo -e "${YELLOW}Cleaning up shell configuration...${NC}"
sed -i '/pyenv/d' ~/.bashrc
sed -i '/PYENV_ROOT/d' ~/.bashrc

echo -e "${GREEN}Cleanup complete!${NC}"
echo -e "${YELLOW}You may need to restart your terminal for all changes to take effect.${NC}" 