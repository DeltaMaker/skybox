# websocket_server/__init__.py

"""
WebSocket Server Package

This package provides WebSocket server and client implementations for building
real-time applications with both basic and advanced functionality.
"""

# Optionally, include the following import to make it easier to access
from .base_websocket_server import BaseWebSocketServer
from .base_websocket_client import BaseWebSocketClient
from .simple_server import SimpleWebsocketServer
from .simple_client import SimpleWebsocketClient

__all__ = [
    'BaseWebSocketServer',
    'BaseWebSocketClient',
    'SimpleWebsocketServer',
    'SimpleWebsocketClient'
]