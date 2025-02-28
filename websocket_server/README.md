# WebSocket Server Package

This package provides WebSocket server and client implementations for building real-time applications.

## Components

- **BaseWebSocketServer**: Advanced WebSocket server with client management
- **BaseWebSocketClient**: Advanced WebSocket client with connection management
- **SimpleWebsocketServer**: Simplified WebSocket server with broadcast capability
- **SimpleWebsocketClient**: Simplified WebSocket client for easy integration

## Examples

The `examples` directory contains reference implementations:

- **example_server.py**: Basic server broadcasting random data
- **example_client.py**: Client receiving and processing server data
- **skylight_client.py**: Client for the Skylight LED control system
- **camera_viewer.py**: Client for viewing camera streams with vision overlays

## Usage

See the examples for detailed usage patterns. Basic usage:

```python
from websocket_server.simple_server import SimpleWebsocketServer
from websocket_server.simple_client import SimpleWebsocketClient

# Create server and client instances
server = SimpleWebsocketServer()
client = SimpleWebsocketClient()

# Start server and client
server.start()
client.start()
```
