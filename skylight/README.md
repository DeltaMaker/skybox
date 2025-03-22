# Skylight Server

## Architecture Overview

### SkylightServer v2
The current implementation uses a clean, modular architecture:
- Inherits from `SimpleWebsocketServer`
- Uses composition with `SimpleWebsocketClient` instances
- Separates server and client functionality
- Provides explicit client objects for each connection (Moonraker, Skybox)

### Key Components
1. **Client Connection Management**
   - Dedicated client objects for each service
   - Service-specific callback handlers
   - Explicit error handling per client

2. **Message Handling**
   - Dedicated handlers for each client type:
     - `handle_moonraker_update`
     - `handle_skybox_update`
   - Clear message parsing logic
   - Service-specific state management

3. **LED Control**
   - Preset management
   - Scene format handling
   - Brightness control
   - Overlay sending mechanism

## WebSocket API

### Connection Endpoint
```
ws://localhost:7120/websocket
```

Clients receive real-time state updates in the following format:
```json
{
    "timestamp": "<current_time>",
    "state": {
        "update_interval": "<interval>",
        "scene": {},
        "skylight": {
            "status": "on|off",
            "chain_count": "<led_count>",
            "preset_scene": "<current_scene>",
            "brightness": "<0-255>",
            "error": null
        },
        "moonraker": {
            "temperature": "<current_temp>",
            "target": "<target_temp>",
            "progress": "<0-1>",
            "state": "<printer_state>",
            "is_paused": "<boolean>"
        }
    }
}
```

## HTTP API Endpoints

### 1. Status Endpoint
```
GET /skylight/status
```
Returns the current state of the system including LED and printer status.

### 2. Control Endpoint
```
GET/POST /skylight/control
```

Parameters:
- `brightness`: Integer (0-255) - Set LED brightness
- `action`: String
  - `"on"` - Turn system on
  - `"off"` - Turn system off

Example calls:
```bash
# Set brightness
curl -X POST http://localhost:7120/skylight/control -d '{"brightness": 128}'

# Turn system on
curl -X POST http://localhost:7120/skylight/control -d '{"action": "on"}'
```

### 3. Scene Control Endpoint
```
GET/POST /skylight/scene
```

Parameters:
- `format`: JSON array of LED patterns
- `values`: JSON array of values for the patterns
- `preset`: String - Name of preset scene

Available presets:
- `"temperature"` - Blue to red fade based on temperature
- `"progress"` - Green progress indicator
- `"paused"` - Yellow breathing effect
- `"ready"` - Blue-green blend
- `"idle"` - White chase effect
- `"rainbow"` - Rainbow pattern
- `"data"` - Custom data visualization

## LED Pattern Formats

Each pattern in the format array follows the structure:
```python
[pattern_type, start_led, end_led, color1, color2, option]
```

Available patterns:
- `"fade"` - Gradient between two colors
- `"progress"` - Progress bar effect
- `"breathe"` - Pulsing effect
- `"blend"` - Color blending
- `"chase"` - Moving light pattern
- `"rainbow"` - Rainbow effect
- `"output"` - Data visualization

Example format:
```json
{
    "format": [
        ["fade", 0, 30, "blue", "red", 0],
        ["chase", 0, 30, "white", "black", 0]
    ]
}
```

## Usage Examples

### Using Python requests
```python
import requests
import json

# Set a preset scene
requests.post('http://localhost:7120/skylight/scene', 
             json={"preset": "rainbow"})

# Set custom format
format_data = [["fade", 0, 30, "blue", "red", 0]]
requests.post('http://localhost:7120/skylight/scene', 
             json={"format": format_data})

# Update values
requests.post('http://localhost:7120/skylight/scene', 
             json={"values": [0.5]})
```

### Using Python websockets
```python
import asyncio
import websockets
import json

async def set_scene():
    uri = "ws://localhost:7120/websocket"
    async with websockets.connect(uri) as websocket:
        # Set a preset scene
        await websocket.send(json.dumps({
            "method": "set_scene",
            "params": {"preset": "rainbow"}
        }))

        # Set custom format
        format_data = [["fade", 0, 30, "blue", "red", 0]]
        await websocket.send(json.dumps({
            "method": "set_scene",
            "params": {"format": format_data}
        }))

# Run the async function
asyncio.run(set_scene())
```

## Debug Mode

When debug is enabled, the server provides additional logging:
- Client connections/disconnections
- State changes
- LED updates
- Error details

To enable debug mode, set `debug=True` in the server initialization or use the configuration file.
