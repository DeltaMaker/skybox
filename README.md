# skybox

 DeltaMaker SkyBox Software

This software consists of several services which implement the automated control and vision system for
the DeltaMaker Motion System and DeltaMaker 3D Printer.

The following services are implemented in Python and run as Flask apps::

netinfo     Network Info Webpage

The netinfo service generates a simple webpage that displays the Ethenet IP address which has been
assign by DHCP. The webpage is typically accessed by connecting to the DeltaMaker's WiFi hotspot and browsing to 
the following address: http://192.168.10.1/info


skybox-cv   Skybox Vision System


The skybox-cv service replaces the standard WebCam service used by OctoPrint. Before starting skybox-cv, the 
webcamd service should be disabled.

     $ sudo systemctl disable webcamd

The skybox-cv software is started as follows:

     $ sudo service skybox restart





-------------

Research Notes

3/1/2022

DeltaMaker Pro
Work volume: 470mm diameter by 290mm high
 or 400mm diameter by 320mm high

Move end-effector out of camera view:
        G1 X0 Y240 Z260
        G1 X0 Y235 Z295




2/27/2022

DeltaMaker Jr. 
Work volume: 240mm diameter by 120mm high

Move end-effector out of camera view:
	G1 X0 Y100 Z20

Turn light to bright white, for camera:
	CAMERA_LIGHT_ON

Capture high-res image:
	???

Turn off white light:
	CAMERA_LIGHT_OFF

Move end-effector to top-center:
	G1 X0 Y0 Z120


