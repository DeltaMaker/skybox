import cv2
import numpy as np
import cv2.aruco as aruco
import json


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
    def __init__(self, marker_size=0.01, dictionary_id=cv2.aruco.DICT_4X4_100, 
                 camera_matrix=None, distortion_coeffs=None, is_frame_undistorted=True, debug=False):
        """
        Initialize the marker tracker.
        
        Args:
            marker_size: Physical size of the markers in meters (useful for pose estimation)
            dictionary_id: ArUco dictionary to use for marker detection
            camera_matrix: Pre-loaded camera matrix for pose estimation
            distortion_coeffs: Pre-loaded distortion coefficients
            is_frame_undistorted: Whether frames passed to process_frame are already undistorted
            debug: Enable debug output
        """
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
        self.detector = cv2.aruco  # Use the aruco module directly for detecting markers
        self.marker_size = marker_size
        self.debug = debug
        self.is_frame_undistorted = is_frame_undistorted
        
        # Store calibration info
        self.camera_matrix = camera_matrix
        self.distortion_coeffs = distortion_coeffs
        self.corners = self.ids = None

    def process_frame(self, frame):
        """Detect ARUCO markers in the frame and return normalized coordinates.
        
        Args:
            frame: OpenCV image in BGR format
            
        Returns:
            List of dictionaries containing marker data with normalized coordinates (0-1)
            where (0,0) is top-left and (1,1) is bottom-right of the frame.
            Coordinates are truncated to 4 decimal places.
        """
        height, width = frame.shape[:2]
        if self.debug:
            print(f"Processing frame with size {width}x{height}")
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect markers with standard parameters
        # No longer passing cameraMatrix/distCoeff to detectMarkers as they're not valid parameters
        self.corners, self.ids, _ = self.detector.detectMarkers(
            gray, self.aruco_dict
        )
        
        marker_data = []

        if self.ids is not None:
            for marker_id, marker_corners in zip(self.ids.flatten(), self.corners):
                # Normalize corner coordinates and truncate to 4 decimal places
                corners_array = marker_corners.flatten()
                normalized_corners = []
                for i in range(0, len(corners_array), 2):
                    x = round(corners_array[i] / width, 4)
                    y = round(corners_array[i + 1] / height, 4)
                    normalized_corners.extend([x, y])
                
                marker_data.append({
                    "id": marker_id,
                    "corners": normalized_corners
                })

        return convert_numpy_types(marker_data)

    def get_detected_ids(self):
        """Get the list of detected marker IDs."""
        if self.ids is None:
            return []
        return self.ids.flatten().tolist()
