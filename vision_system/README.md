# Vision System

A flexible computer vision system that provides real-time video streaming with marker detection and hand tracking capabilities.

## Features

- Multiple camera source support (OpenCV, HTTP streams)
- Real-time video streaming over WebSocket
- ArUco marker detection and tracking
- Hand landmark detection and tracking
- Configurable frame rates and resolutions
- Mirror mode support
- Performance monitoring
- Debug mode for development

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Install dependencies:
```bash
pip install opencv-python numpy websockets requests
```

## Components

### Camera Server

The server component captures video from a camera source and streams it to connected clients.

#### Usage

1. Basic usage:
```bash
python camera_server.py
```

2. With configuration:
```bash
python camera_server.py --host 0.0.0.0 --port 7160 --camera 0 --debug
```

Options:
- `--host`: Host address to bind to (default: 0.0.0.0)
- `--port`: Port number to listen on (default: 7160)
- `--camera`: Camera device ID for OpenCV (default: 0)
- `--debug`: Enable debug output

### Camera Viewer

The viewer component connects to the server and displays the video stream with visualization overlays.

#### Usage

1. Basic usage:
```bash
python camera_viewer.py
```

2. With configuration:
```bash
python camera_viewer.py \
    --ws_uri ws://192.168.1.248:7160/websocket \
    --width 640 \
    --height 400 \
    --fps 15 \
    --mirror \
    --hands \
    --debug
```

Options:
- `--ws_uri`: WebSocket server address
- `--width`: Display width (default: 640)
- `--height`: Display height (default: 400)
- `--fps`: Target frame rate (default: 15)
- `--mirror`: Mirror the image horizontally
- `--hands`: Enable hand tracking visualization
- `--debug`: Show debug information

## Example Setups

### Local Development
```bash
# Terminal 1 - Start server
python camera_server.py --debug

# Terminal 2 - Start viewer
python camera_viewer.py --ws_uri ws://localhost:7160/websocket --debug
```

### Network Setup
```bash
# On Server Machine (e.g., Raspberry Pi)
python camera_server.py --host 0.0.0.0 --port 7160

# On Client Machine
python camera_viewer.py --ws_uri ws://192.168.1.248:7160/websocket
```

## Viewer Controls

- Press 'q' to quit the viewer
- Window shows:
  - Live video feed
  - Detected ArUco markers (green boxes with IDs)
  - Hand tracking landmarks (if enabled)
  - FPS information (in debug mode)

## Development

### Adding New Camera Types

1. Create a new class inheriting from `CameraServer`
2. Implement required methods:
   - `_setup_camera()`
   - `_capture_frame()`
   - `_cleanup_camera()` (optional)

Example:
```python
class CustomCamera(CameraServer):
    def _setup_camera(self):
        # Initialize your camera
        pass

    def _capture_frame(self):
        # Capture and return a frame
        pass
```

## Troubleshooting

1. No video display:
   - Check if server is running
   - Verify WebSocket URI is correct
   - Ensure camera ID is valid

2. Poor performance:
   - Reduce resolution
   - Lower target FPS
   - Check network bandwidth

3. Connection errors:
   - Verify host/port settings
   - Check network connectivity
   - Ensure no firewall blocking

## Version History

- 0.1 (2025-03-22): Initial release
  - Basic camera support
  - Marker tracking
  - Hand tracking
  - Network streaming

## Author

Bob Houston
