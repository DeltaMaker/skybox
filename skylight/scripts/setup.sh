#!/bin/bash
# This script installs Skybox on a Raspberry Pi

PYTHONDIR="${HOME}/skybox-env"
AIVISIONDIR="${HOME}/AIVisionApp"

# Step 1: Install system packages
install_packages()
{
    # Packages for python cffi
    #PKGLIST="virtualenv python-dev libffi-dev build-essential"

    # Update system package info
    report_status "Running apt-get update..."
    sudo apt-get update

    # Install desired packages
    #report_status "Installing packages..."
    #sudo apt-get install --yes ${PKGLIST}
}

# Step 2: Create python virtual environment
create_virtualenv()
{
    report_status "Updating python virtual environment..."

    # Create virtualenv if it doesn't already exist
    [ ! -d ${PYTHONDIR} ] && virtualenv -p python3 ${PYTHONDIR}

    # Install/update dependencies
    ${PYTHONDIR}/bin/pip install -r ${SRCDIR}/scripts/requirements.txt
}

# Step 3: Install startup script
install_script()
{
    report_status "Installing system start script..."
    sudo cp "${SRCDIR}/scripts/skylight-start.sh" /etc/init.d/skylight
    sudo update-rc.d skylight defaults
}

# Step 4: Install startup script config
install_config()
{
    DEFAULTS_FILE=/etc/default/skylight
    [ -f $DEFAULTS_FILE ] && return

    report_status "Installing system start configuration..."
    sudo /bin/sh -c "cat > $DEFAULTS_FILE" <<EOF
# Configuration for /etc/init.d/skylight

SKYBOX_USER=$USER

SKYBOX_EXEC="sudo ${PYTHONDIR}/bin/python"

SKYBOX_ARGS="${AIVISIONDIR}/skylight/skylight_server.py -f ${AIVISIONDIR}/examples/localhost.conf"

EOF
}

# Step 5: Start host software
start_software()
{
    report_status "Launching Skylight host software..."
    sudo /etc/init.d/skylight restart
}

# Helper functions
report_status()
{
    echo -e "\n\n###### $1"
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

# Force script to exit if an error occurs
set -e

# Find SRCDIR from the pathname of this script
SRCDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. && pwd )"

# Run installation steps defined above
verify_ready
install_packages
create_virtualenv
install_script
install_config
start_software
