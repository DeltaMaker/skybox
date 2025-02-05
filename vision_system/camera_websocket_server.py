import asyncio
import websockets
import io
from threading import Condition
import json
import cv2
import numpy as np
from aiohttp import web
import logging
#from vision_system.marker_tracker import MarkerTracker
from marker_tracker import MarkerTracker
from hand_tracker import HandTracker

# Attempt to import Picamera2
try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput

    PICAMERA2_AVAILABLE = True
    print("Picamera2 is available.")
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("Picamera2 not available. Using OpenCV's VideoCapture instead.")


class CameraServer:
    def __init__(self, host='0.0.0.0', port=7160, camera_id=0):
        self.host = host
        self.port = port
        self.clients = {}  # Store clients with their configurations
        self.running = False
        self.base_size = None  # The camera's current resolution
        self.marker_tracker = MarkerTracker()  # For ARUCO marker detection
        self.hand_tracker = HandTracker()  # For hand detection

        # Initialize camera depending on whether Picamera2 is available
        if PICAMERA2_AVAILABLE:
            self.picam2 = Picamera2()
            self.output = StreamingOutput()
            self.initialize_picamera2()
        else:
            self.camera_id = camera_id
            self.cap = cv2.VideoCapture(self.camera_id)  # Use OpenCV's VideoCapture
            if not self.cap.isOpened():
                raise Exception("Error: Camera not accessible using cv2.VideoCapture.")

    def initialize_picamera2(self):
        """Initialize Picamera2 if available."""
        sensor_modes = self.picam2.sensor_modes
        if sensor_modes:
            max_mode = max(sensor_modes, key=lambda x: x['size'][0] * x['size'][1])
            full_res = max_mode['size']
        else:
            full_res = (2304, 1296)

        video_config = self.picam2.create_video_configuration(
            main={"size": (640, 480)},
            lores=None,
            raw={"size": full_res},
            buffer_count=4,
            controls={
                "FrameDurationLimits": (33333, 33333),  # ~30fps
                "NoiseReductionMode": 2,  # Higher noise reduction (0=Off, 1=Fast, 2=High Quality)
                "Sharpness": 2.0,         # Increased sharpness (range is -1.0 to 16.0)
                "Brightness": 0.0,        # Normal brightness (range is -1.0 to 1.0)
                "Contrast": 1.0,          # Normal contrast (range is 0.0 to 32.0)
                "Saturation": 1.0,        # Normal saturation (range is 0.0 to 32.0)
                "ExposureValue": 0,       # Auto exposure
                "AwbEnable": 1,           # Enable Auto White Balance
                "AeEnable": 1,            # Enable Auto Exposure
            }
        )
        self.picam2.configure(video_config)

    def get_current_frame(self):
        """Capture the current frame from the camera."""
        if PICAMERA2_AVAILABLE:
            frame = self.output.frame
            if frame:
                # Convert the binary frame (MJPEG) to an image (OpenCV format)
                np_arr = np.frombuffer(frame, np.uint8)
                return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        else:
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    async def start_server(self):
        """Start the combined HTTP and WebSocket server."""
        app = web.Application()

        # Add routes for WebSocket and HTTP requests
        app.router.add_route('GET', '/websocket', self.websocket_handler)
        app.router.add_route('GET', '/status', self.http_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        print(f"Server started on ws://{self.host}:{self.port} (WebSocket and HTTP)")

        # Start the frame sending task
        asyncio.create_task(self.send_frames_loop())

        # Keep the server running
        while True:
            await asyncio.sleep(3600)

    async def websocket_handler(self, request):
        """Handle client subscriptions for camera frames."""
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)

        try:
            # Receive client subscription settings
            config_message = await ws.receive()

            if config_message.type == web.WSMsgType.TEXT:
                config = json.loads(config_message.data)

                # Extract custom frame size, FPS, and mirror flag from client subscription
                custom_size = tuple(config.get('size', (640, 480)))
                custom_fps = config.get('fps', 15)
                mirror = config.get('mirror', False)
                track_hands = config.get('hands', False)  # New flag

                print(f"New client subscribed with size={custom_size}, fps={custom_fps}, mirror={mirror}")

                # Start the camera with the first client's resolution
                if not self.running:
                    if PICAMERA2_AVAILABLE:
                        self.start_picamera2(custom_size, custom_fps)
                    else:
                        if not self.cap.isOpened():
                            self.cap = cv2.VideoCapture(self.camera_id)
                        self.base_size = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                                        int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
                    self.running = True

                # Add client to the list with their settings
                self.clients[ws] = {
                    'size': custom_size,
                    'fps': custom_fps,
                    'mirror': mirror,
                    'hands': track_hands  # Store the flag
                }

                # Send subscription confirmation to the client
                confirmation_message = {
                    'status': 'subscribed',
                    'size': custom_size,
                    'fps': custom_fps,
                    'mirror': mirror,
                    'hands': track_hands
                }
                await ws.send_str(json.dumps(confirmation_message))

                # Keep the connection alive and handle incoming messages
                try:
                    async for msg in ws:
                        if msg.type == web.WSMsgType.ERROR:
                            print(f'WebSocket connection closed with exception {ws.exception()}')
                            break
                        elif msg.type == web.WSMsgType.CLOSE:
                            print('WebSocket connection closed normally')
                            break
                finally:
                    if ws in self.clients:
                        del self.clients[ws]
                    if not self.clients:
                        self.stop_camera()

        except Exception as e:
            logging.error(f"Error in websocket handler: {e}")
        
        return ws

    def start_picamera2(self, size, fps):
        """Start the Picamera2 camera with the specified settings."""
        sensor_modes = self.picam2.sensor_modes
        if sensor_modes:
            max_mode = max(sensor_modes, key=lambda x: x['size'][0] * x['size'][1])
            full_res = max_mode['size']
        else:
            full_res = (2304, 1296)

        video_config = self.picam2.create_video_configuration(
            main={"size": size},
            lores=None,
            raw={"size": full_res},
            buffer_count=4,
            controls={
                "FrameDurationLimits": (int(1/fps * 1000000), int(1/fps * 1000000)),
                "NoiseReductionMode": 2,  # Higher noise reduction
                "Sharpness": 2.0,         # Increased sharpness
                "Brightness": 0.0,        # Normal brightness
                "Contrast": 1.0,          # Normal contrast
                "Saturation": 1.0,        # Normal saturation
                "ExposureValue": 0,       # Auto exposure
                "AwbEnable": 1,           # Enable Auto White Balance
                "AeEnable": 1,            # Enable Auto Exposure
            }
        )
        self.picam2.configure(video_config)
        self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
        self.base_size = size
        print(f"Picamera2 started with size={size}, fps={fps}")

    async def send_frames_loop(self):
        """Continuous loop to send frames to all connected clients."""
        while True:
            if self.clients:
                await self.send_frames_and_markers()
            await asyncio.sleep(0.01)  # Small delay to prevent CPU overload

    async def send_frames_and_markers(self):
        """Send frames to connected clients, resizing once per unique size and sending marker data."""
        try:
            while self.clients:
                frame = self.get_current_frame()

                if frame is not None:
                    # Group clients by their requested size
                    clients_by_size = {}
                    for client_ws, client_info in self.clients.items():
                        size = client_info['size']
                        if size not in clients_by_size:
                            clients_by_size[size] = {
                                'mirror': [], 
                                'no_mirror': [],
                                'hands': False,
                                'size': size
                            }
                        # Sub-group by mirror flag
                        if client_info.get('mirror', False):
                            clients_by_size[size]['mirror'].append(client_ws)
                        else:
                            clients_by_size[size]['no_mirror'].append(client_ws)
                        # Update track_hands if any client needs it
                        if client_info.get('hands', False):
                            clients_by_size[size]['hands'] = True

                    # Process hand tracking once at the largest size that needs it
                    hand_data = None
                    largest_resized_frame = None
                    if any(info['hands'] for info in clients_by_size.values()):
                        # Find largest size that needs hand tracking
                        largest_size = max(
                            (info['size'] for info in clients_by_size.values() if info['hands']),
                            key=lambda s: s[0] * s[1]
                        )
                        # Process hands once at largest size
                        largest_resized_frame = self.get_resized_frame(frame, largest_size)
                        hand_data = self.hand_tracker.process_frame(largest_resized_frame)

                    # Process each unique size
                    for size, size_info in clients_by_size.items():
                        # Reuse the largest resized frame if available and matching the current size
                        if largest_resized_frame is not None and size == largest_size:
                            resized_frame = largest_resized_frame
                        else:
                            resized_frame = self.get_resized_frame(frame, size)
                        
                        # Process non-mirrored frame
                        if size_info['no_mirror']:
                            marker_data = self.marker_tracker.process_frame(resized_frame)
                            
                            _, encoded_frame = cv2.imencode('.jpg', resized_frame)
                            frame_bytes = encoded_frame.tobytes()
                            
                            for client_ws in size_info['no_mirror']:
                                if not client_ws.closed:
                                    try:
                                        await client_ws.send_str(json.dumps({
                                            "markers": marker_data,
                                            "hands": hand_data if self.clients[client_ws]['hands'] else []
                                        }))
                                        await client_ws.send_bytes(frame_bytes)
                                    except Exception as e:
                                        logging.error(f"Error sending frame/data: {e}")
                                        if client_ws in self.clients:
                                            del self.clients[client_ws]

                # Adjust sleep rate for frame sending based on FPS
                if self.clients:
                    await asyncio.sleep(1 / min(client['fps'] for client in self.clients.values()))
                else:
                    await asyncio.sleep(1)  # Sleep to avoid a busy loop if no clients connected

        except Exception as e:
            logging.error(f"Error sending frames: {e}")

    def get_resized_frame(self, frame, client_size):
        """Resize the frame to match the client's requested size."""
        resized_frame = cv2.resize(frame, client_size)
        return resized_frame

    def stop_camera(self):
        """Stop the camera when no clients are connected."""
        if PICAMERA2_AVAILABLE:
            self.picam2.stop_recording()
        else:
            self.cap.release()
        self.running = False
        print("Camera stopped")

    async def http_handler(self, request):
        """Handle HTTP requests to get the current status of connected clients."""
        clients_status = [{'size': client_info['size'], 'fps': client_info['fps'], 'mirror': client_info['mirror'], 'hands': client_info['hands']}
                          for client_info in self.clients.values()]
        return web.json_response({
            'status': 'running' if self.running else 'stopped',
            'base_size': self.base_size if self.base_size else 'N/A',  # Base frame size of the camera
            'subscribers': clients_status
        })

    def run(self):
        """Run the WebSocket server."""
        asyncio.run(self.start_server())


def convert_numpy_types(obj):
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


class MarkerTracker:
    def __init__(self, marker_size=0.01, total_markers=50, dictionary_id=cv2.aruco.DICT_4X4_50):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
        self.detector = cv2.aruco  # Use the aruco module directly for detecting markers
        self.marker_size = marker_size
        self.camera_matrix, self.distortion_coeffs = self.default_camera_calibration()
        self.corners = self.ids = None

    def default_camera_calibration(self, image_width=640, image_height=480):
        focal_length = image_width if image_width > image_height else image_height
        center = (image_width / 2, image_height / 2)
        camera_matrix = np.array([[focal_length, 0, center[0]],
                                  [0, focal_length, center[1]],
                                  [0, 0, 1]], dtype="double")
        distortion_coeffs = np.zeros((4, 1))
        return camera_matrix, distortion_coeffs

    def process_frame(self, frame):
        """Detect ARUCO markers in the frame."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.corners, self.ids, _ = self.detector.detectMarkers(gray, self.aruco_dict)
        marker_data = []

        if self.ids is not None:
            for marker_id, marker_corners in zip(self.ids.flatten(), self.corners):
                marker_data.append({
                    "id": marker_id,
                    "corners": marker_corners.flatten()
                })

        return convert_numpy_types(marker_data)

    def get_detected_ids(self):
        """Get the list of detected marker IDs."""
        if self.ids is None:
            return []
        return self.ids.flatten().tolist()


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Save the latest frame."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def main():
    # Initialize and run the Camera WebSocket and HTTP server
    camera_server = CameraServer(host='0.0.0.0', port=7160)

    try:
        camera_server.run()
    except KeyboardInterrupt:
        print("Stopping Camera Server...")


if __name__ == "__main__":
    main()