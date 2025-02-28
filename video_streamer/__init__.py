"""
Video Streamer - HTTP and WebSocket-based video streaming package.

This package provides components for streaming video over HTTP and WebSocket connections:

Core Components:
- StreamingModule: Base streaming server implementation with MJPEG support
- OverlayManager: Graphics overlay system for video streams
- VideoCapture: Unified interface for different video sources

The architecture supports:
- MJPEG streaming over HTTP
- WebSocket frame transmission
- Multiple simultaneous clients
- Real-time graphics overlays
- Various video sources (webcam, IP camera, files)
"""

from .streaming_module import StreamingOutput, StreamingHandler, StreamingServer
from .overlay_manager import OverlayManager
from .video_capture import VideoCapture 