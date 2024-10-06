#!/bin/bash

# Variables
REPO="deltamaker/skybox.git"            # Replace with your SKYBOX repository URL
SERVICE="/etc/systemd/system/video_streamer.service"
INSTALL_PATH="${HOME}/skybox"          # Directory where SKYBOX will be installed
SCRIPTS_DIR="${INSTALL_PATH}/scripts"    # Path to the scripts directory
PYTHONDIR="${HOME}/skybox-env"         # Python virtual environment directory
REQUIREMENTS="${SCRIPTS_DIR}/requirements.txt"   # Path to requirements.txt in scripts directory
DEFAULTS_FILE="/etc/default/video_streamer"    # Path to the /etc/default/video_streamer file
CONFIG_PATH="${SCRIPTS_DIR}/skylight.conf" # Path to config file in scripts directory

# Force script to exit if an error occurs
set -e

# Set locale to avoid issues
export LC_ALL=C

# Function to check for root user
verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "[ERROR] This script must not be run as root!"
        exit -1
    fi
}

# Step 1: Preflight checks
preflight_checks() {
    if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F 'video_streamer.service')" ]; then
        echo "[PRE-CHECK] Video Streamer service found!"
    else
        echo "[INFO] Video Streamer service not found, proceeding with installation."
    fi
}

# Step 2: Download or update the repository
check_download() {
    if [ ! -d "${INSTALL_PATH}" ]; then
        echo "[DOWNLOAD] Cloning repository..."
        git clone https://github.com/${REPO} "${INSTALL_PATH}"
    else
        echo "[DOWNLOAD] Repository already found, pulling latest changes..."
        git -C "${INSTALL_PATH}" pull
    fi
}

# Step 3: Create Python virtual environment and install dependencies
create_virtualenv() {
    echo "[VIRTUALENV] Setting up Python environment..."
    
    # Create virtualenv if it doesn't already exist
    if [ ! -d "${PYTHONDIR}" ]; then
        virtualenv -p python3 "${PYTHONDIR}"
    fi

    # Install/update dependencies from requirements.txt
    echo "[VIRTUALENV] Installing dependencies from ${REQUIREMENTS}..."
    ${PYTHONDIR}/bin/pip install -r "${REQUIREMENTS}"
}

# Step 4: Create /etc/default/video_streamer file dynamically
create_defaults_file() {
    echo "[CONFIG] Creating /etc/default/video_streamer file..."

    sudo /bin/sh -c "cat > ${DEFAULTS_FILE}" <<EOF
# Configuration for Video Streamer Daemon

# Path to the Python executable in the virtual environment
SKYLIGHT_EXEC=/home/pi/skybox-env/bin/python

# Path to the Video Streamer configuration file
SKYLIGHT_CONF=/home/pi/skybox/scripts/skylight.conf
EOF

    echo "[CONFIG] /etc/default/video_streamer file created!"
}

# Step 5: Create and install systemd service
install_service() {
    echo "[INSTALL] Installing Video Streamer service..."

    # Overwrite the service file each time
    S=$(<"${SCRIPTS_DIR}/video_streamer.service")
    S=$(sed "s|TC_USER|$(whoami)|g" <<< "$S")

    # Write the service file to /etc/systemd/system/
    echo "$S" | sudo tee "${SERVICE}" > /dev/null

    # Verify that the service file has been overwritten
    echo "[DEBUG] Video Streamer service file contents:"
    cat "${SERVICE}"

    # Reload systemd to pick up the new service file
    sudo systemctl daemon-reload

    # Enable and start the Video Streamer service
    sudo systemctl enable video_streamer.service
    sudo systemctl start video_streamer.service

    echo "[INSTALL] Video Streamer service installed, enabled, and started!"
}

# Step 6: Start the Video Streamer service
start_service() {
    echo "[SERVICE] Starting Video Streamer service..."
    sudo systemctl restart video_streamer.service
    echo "[SERVICE] Video Streamer service started!"
}

# Helper function for reporting status
report_status() {
    echo -e "\n###### $1"
}

# Start the installation process
verify_ready
preflight_checks
check_download
create_virtualenv
#create_defaults_file
install_service
start_service
