#!/bin/bash
# Uninstall script for raspbian/debian type installations

# Stop Skylight Service
echo "#### Stopping Skylight Service.."
sudo service skylight stop

# Remove Skylight from Startup
echo
echo "#### Removing Skylight from Startup.."
sudo update-rc.d -f skylight remove

# Remove Skylight from Services
echo
echo "#### Removing Skylight Service.."
sudo rm -f /etc/init.d/skylight /etc/default/skylight

# Notify user of method to remove Skybox source code
echo
echo "The Skybox system files have been removed."
echo
echo "The following command is typically used to remove local files:"
echo "  rm -rf ~/skybox-env ~/skybox"
