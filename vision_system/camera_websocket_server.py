import asyncio
import websockets
import io
from threading import Condition
import json
import cv2
import numpy as np
from aiohttp import web
import logging

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
        # Start the camera with the default size and framerate.
        video_config = self.picam2.create_video_configuration(main={"size": (640, 480)})
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
                    'mirror': mirror
                }

                # Send subscription confirmation to the client
                confirmation_message = {
                    'status': 'subscribed',
                    'size': custom_size,
                    'fps': custom_fps,
                    'mirror': mirror
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
        video_config = self.picam2.create_video_configuration(main={"size": size}, controls={"FrameRate": fps})
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
                    # First group clients by their requested size
                    clients_by_size = {}
                    for client_ws, client_info in self.clients.items():
                        size = client_info['size']
                        if size not in clients_by_size:
                            clients_by_size[size] = {'mirror': [], 'no_mirror': []}
                        # Sub-group by mirror flag
                        if client_info.get('mirror', False):
                            clients_by_size[size]['mirror'].append(client_ws)
                        else:
                            clients_by_size[size]['no_mirror'].append(client_ws)

                    # Process each unique size
                    for size, mirror_groups in clients_by_size.items():
                        # Resize frame once per unique size
                        resized_frame = self.get_resized_frame(frame, size)
                        print(f"Resized frame to {size}, shape={resized_frame.shape}")
                        
                        # Process non-mirrored frame and detect markers
                        if mirror_groups['no_mirror']:
                            marker_data = self.marker_tracker.process_frame(resized_frame)
                            _, encoded_frame = cv2.imencode('.jpg', resized_frame)
                            frame_bytes = encoded_frame.tobytes()
                            
                            # Send to all non-mirror clients
                            for client_ws in mirror_groups['no_mirror']:
                                if not client_ws.closed:
                                    try:
                                        await client_ws.send_bytes(frame_bytes)
                                        await client_ws.send_str(json.dumps({"markers": marker_data}))
                                    except Exception as e:
                                        logging.error(f"Error sending frame/markers to client: {e}")
                                        if client_ws in self.clients:
                                            del self.clients[client_ws]
                        
                        # Process mirrored frame if needed
                        if mirror_groups['mirror']:
                            mirrored_frame = cv2.flip(resized_frame, 1)
                            print(f"Flipped frame for size {size}, shape={mirrored_frame.shape}")
                            # Always detect markers on mirrored frame since positions will be different
                            mirrored_marker_data = self.marker_tracker.process_frame(mirrored_frame)
                            _, encoded_frame = cv2.imencode('.jpg', mirrored_frame)
                            frame_bytes = encoded_frame.tobytes()
                            
                            # Send to all mirror clients
                            for client_ws in mirror_groups['mirror']:
                                if not client_ws.closed:
                                    try:
                                        await client_ws.send_bytes(frame_bytes)
                                        await client_ws.send_str(json.dumps({"markers": mirrored_marker_data}))
                                    except Exception as e:
                                        logging.error(f"Error sending frame/markers to client: {e}")
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
        clients_status = [{'size': client_info['size'], 'fps': client_info['fps'], 'mirror': client_info['mirror']}
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