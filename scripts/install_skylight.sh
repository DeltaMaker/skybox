#!/bin/bash

# Variables
REPO="deltamaker/skybox.git"            # Replace with your Skylight repository URL
SERVICE="/etc/systemd/system/skylight.service"
INSTALL_PATH="${HOME}/skybox"          # Directory where Skylight will be installed
SCRIPTS_DIR="${INSTALL_PATH}/scripts"    # Path to the scripts directory
PYTHONDIR="${HOME}/skybox-env"         # Python virtual environment directory
REQUIREMENTS="${SCRIPTS_DIR}/requirements.txt"   # Path to requirements.txt in scripts directory
DEFAULTS_FILE="/etc/default/skylight"    # Path to the /etc/default/skylight file
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
    if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F 'skylight.service')" ]; then
        echo "[PRE-CHECK] Skylight service found!"
    else
        echo "[INFO] Skylight service not found, proceeding with installation."
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

# Step 4: Create /etc/default/skylight file dynamically
create_defaults_file() {
    echo "[CONFIG] Creating /etc/default/skylight file..."

    sudo /bin/sh -c "cat > ${DEFAULTS_FILE}" <<EOF
# Configuration for Skylight Daemon

# Path to the Python executable in the virtual environment
SKYLIGHT_EXEC=/home/pi/skylight-env/bin/python

# Path to the Skylight configuration file
SKYLIGHT_CONF=/home/pi/skylight/scripts/skylight.conf
EOF

    echo "[CONFIG] /etc/default/skylight file created!"
}

# Step 5: Create and install systemd service
install_service() {
    echo "[INSTALL] Installing Skylight service..."

    # Overwrite the service file each time
    S=$(<"${SCRIPTS_DIR}/skylight.service")
    S=$(sed "s|TC_USER|$(whoami)|g" <<< "$S")

    # Write the service file to /etc/systemd/system/
    echo "$S" | sudo tee "${SERVICE}" > /dev/null

    # Verify that the service file has been overwritten
    echo "[DEBUG] Skylight service file contents:"
    cat "${SERVICE}"

    # Reload systemd to pick up the new service file
    sudo systemctl daemon-reload

    # Enable and start the Skylight service
    sudo systemctl enable skylight.service
    sudo systemctl start skylight.service

    echo "[INSTALL] Skylight service installed, enabled, and started!"
}

# Step 6: Start the Skylight service
start_service() {
    echo "[SERVICE] Starting Skylight service..."
    sudo systemctl restart skylight.service
    echo "[SERVICE] Skylight service started!"
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
