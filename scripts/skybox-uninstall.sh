#!/bin/bash
# Uninstall script for raspbian/debian type installations

# Stop Skybox Service
echo "#### Stopping Skybox Service.."
sudo service skybox stop

# Remove Skybox from Startup
echo
echo "#### Removing Skybox from Startup.."
sudo update-rc.d -f skybox remove

# Remove Skybox from Services
echo
echo "#### Removing Skybox Service.."
sudo rm -f /etc/init.d/skybox /etc/default/skybox

# Notify user of method to remove Skybox source code
echo
echo "The Skybox system files have been removed."
echo
echo "The following command is typically used to remove local files:"
echo "  rm -rf ~/skybox-env ~/skybox"
