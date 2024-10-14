import cv2
import numpy as np
import cv2.aruco as aruco
import json

class MarkerTracker:
    def __init__(self, websocket_client=None, marker_size=0.01, total_markers=50, dictionary_id=aruco.DICT_4X4_50, draw=True):
        self.websocket_client = websocket_client  # WebSocket client for sending data
        self.aruco_dict = aruco.getPredefinedDictionary(dictionary_id)
        #self.parameters = aruco.DetectorParameters_create()
        self.detector = aruco  # Use the aruco module directly for detecting markers
        self.marker_size = marker_size
        self.camera_matrix, self.distortion_coeffs = self.default_camera_calibration()
        self.draw = draw
        self.detected_ids = []
        self.crop_rect = None  # Assuming this might be set for image cropping, but not used here
        self.feature_vector = None
        self.corners = self.ids = None

    def default_camera_calibration(self, image_width=640, image_height=480):
        focal_length = image_width if image_width > image_height else image_height
        center = (image_width / 2, image_height / 2)
        camera_matrix = np.array([[focal_length, 0, center[0]],
                                  [0, focal_length, center[1]],
                                  [0, 0, 1]], dtype="double")
        distortion_coeffs = np.zeros((4, 1))
        return camera_matrix, distortion_coeffs

    def get_detected_ids(self):
        return self.detected_ids

    def process_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        #corners, ids, rejected = self.detector.detectMarkers(gray, self.aruco_dict, parameters=self.parameters)
        self.corners, self.ids, rejected = self.detector.detectMarkers(gray, self.aruco_dict)

        if self.ids is None:
            self.detected_ids = None
        else:
            flat_ids = self.ids.flatten().tolist()
            markers_data = []
            for marker_id, marker_corners in zip(flat_ids, self.corners):
                marker_data = {
                    "id": marker_id,
                    "corners": marker_corners.flatten().tolist()
                }
                markers_data.append(marker_data)

            # Update detected_ids for external access if needed
            self.detected_ids = flat_ids

            if self.websocket_client:
                # Serialize and send the marker data
                json_data = json.dumps(markers_data)
                self.websocket_client.send(json_data)

    def render_frame(self, frame):
        if self.draw:
            aruco.drawDetectedMarkers(frame, self.corners, self.ids)
        return frame