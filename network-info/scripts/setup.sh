#!/bin/bash
# This script installs Skybox on a Raspberry Pi

PYTHONDIR="${HOME}/skybox-env"

# Step 1: Install system packages
install_packages()
{
    # Packages for python cffi
    PKGLIST="virtualenv python-dev libffi-dev build-essential"
    # opencv requirements
    #PKGLIST="${PKGLIST} libhdf5-dev libhdf5-serial-dev"
    #PKGLIST="${PKGLIST} libatlas-base-dev libjasper-dev"
    #PKGLIST="${PKGLIST} libqtgui4 libqt4-test"
    #PKGLIST="${PKGLIST} libilmbase23 libopenexr-dev"

    # Update system package info
    report_status "Running apt-get update..."
    sudo apt-get update

    # Install desired packages
    report_status "Installing packages..."
    #sudo apt-get install --yes ${PKGLIST}
}

# Step 2: Create python virtual environment
create_virtualenv()
{
    report_status "Updating python virtual environment..."

    # Create virtualenv if it doesn't already exist
    [ ! -d ${PYTHONDIR} ] && virtualenv -p python3 ${PYTHONDIR}

    # Install/update dependencies
    ${PYTHONDIR}/bin/pip install -r ${SRCDIR}/scripts/netinfo-requirements.txt
}

# Step 3: Install startup script
install_script()
{
    report_status "Installing system start script..."
    sudo cp "${SRCDIR}/scripts/netinfo-start.sh" /etc/init.d/netinfo
    sudo update-rc.d netinfo defaults
}

# Step 4: Install startup script config
install_config()
{
    DEFAULTS_FILE=/etc/default/netinfo
    [ -f $DEFAULTS_FILE ] && return

    report_status "Installing system start configuration..."
    sudo /bin/sh -c "cat > $DEFAULTS_FILE" <<EOF
# Configuration for /etc/init.d/netinfo

SKYBOX_USER=$USER

SKYBOX_EXEC=${PYTHONDIR}/bin/python

SKYBOX_ARGS="${SRCDIR}/netinfo.py ${HOME}/printer.cfg -l /tmp/netinfo.log"

EOF
}

# Step 5: Start host software
start_software()
{
    report_status "Launching Skybox host software..."
    sudo /etc/init.d/netinfo restart
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
