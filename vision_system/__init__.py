"""
Vision System - WebSocket-based camera streaming and computer vision package.

This package provides a framework for streaming camera data and computer vision results 
over WebSocket connections. It includes:

Core Components:
- SimpleWebsocketServer: Base server class for broadcasting data to multiple clients
- SimpleWebsocketClient: Base client class for receiving broadcast data
- CameraServer: Specialized server for streaming camera frames and vision results
- CameraViewer: Client for displaying camera streams and vision overlays

Example Implementation:
- ExampleServer: Demo server showing basic broadcast functionality
- ExampleClient: Demo client showing message handling patterns

The architecture supports:
- Multiple simultaneous client connections
- Client-specific configurations (resolution, FPS, etc.)
- Real-time vision processing (markers, hand tracking)
- Binary (frames) and JSON (metadata) message types
- Clean connection lifecycle management

Usage:
    See example_server.py and example_client.py for basic usage patterns.
    See camera_server.py and camera_viewer.py for vision-specific implementations.
"""

from .camera_websocket_server import CameraServer
from .marker_tracker import MarkerTracker
from .hand_tracker import HandTracker
