# websocket_server/__init__.py

"""
WebSocket Server Package

This package provides WebSocket server and client implementations for building
real-time applications with both basic and advanced functionality.
"""

# Optionally, include the following import to make it easier to access
from .simple_server import SimpleWebsocketServer
from .simple_client import SimpleWebsocketClient

__all__ = [
    'SimpleWebsocketServer',
    'SimpleWebsocketClient'
]