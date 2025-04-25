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
        # In newer OpenCV versions (4.7+), we need to use the new ArUco API
        try:
            # First try the modern API (OpenCV 4.7+)
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
            self.parameters = cv2.aruco.DetectorParameters()
            self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.parameters)
            self.use_new_api = True
            if debug:
                print("Using new ArUco detector API")
        except (AttributeError, TypeError):
            # Fall back to the old API
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
            try:
                self.parameters = cv2.aruco.DetectorParameters_create()
                self.parameters.adaptiveThreshConstant = 10
                self.parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            except AttributeError:
                # If even this fails, just use without parameters
                self.parameters = None
            self.detector = cv2.aruco  # Use the aruco module directly
            self.use_new_api = False
            if debug:
                print("Using legacy ArUco detector API")

        self.marker_size = marker_size
        self.debug = debug
        self.is_frame_undistorted = is_frame_undistorted
        
        # Store calibration info
        if camera_matrix is not None and distortion_coeffs is not None:
            self.camera_matrix = camera_matrix
            self.distortion_coeffs = distortion_coeffs
        else:
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
        
        # Detect markers using the appropriate API
        if self.use_new_api:
            # New API (OpenCV 4.7+)
            corners, ids, rejected = self.detector.detectMarkers(gray)
        else:
            # Legacy API
            if self.parameters is not None:
                corners, ids, rejected = self.detector.detectMarkers(
                    gray, self.aruco_dict, parameters=self.parameters
                )
            else:
                corners, ids, rejected = self.detector.detectMarkers(
                    gray, self.aruco_dict
                )
                
        self.corners = corners
        self.ids = ids
        
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
