import cv2
import numpy as np
import cv2.aruco as aruco
import json
import os


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


def load_camera_calibration(calibration_file, debug=False):
    """
    Load camera calibration parameters from a file.
    Falls back to default calibration if file is not available.
    
    Args:
        calibration_file: Path to the calibration file
        debug: Enable debug output
        
    Returns:
        Tuple of (camera_matrix, distortion_coefficients)
    """
    try:
        if os.path.exists(calibration_file):
            with open(calibration_file, 'r') as f:
                calibration_data = json.load(f)
            
            camera_matrix = np.array(calibration_data['camera_matrix'])
            distortion_coeffs = np.array(calibration_data['distortion_coefficients'])
            
            if debug:
                print(f"Loaded camera calibration from {calibration_file}")
                print(f"Camera matrix shape: {camera_matrix.shape}")
                print(f"Distortion coefficients shape: {distortion_coeffs.shape}")
            
            return camera_matrix, distortion_coeffs
    except Exception as e:
        if debug:
            print(f"Error loading calibration file: {e}")
            print("Using default camera calibration")
    
    # Fall back to default calibration
    return default_camera_calibration()


def default_camera_calibration(image_width=640, image_height=480):
    """
    Create a default camera calibration matrix for when calibration data is not available.
    
    Args:
        image_width: Width of the input images
        image_height: Height of the input images
        
    Returns:
        Tuple of (camera_matrix, distortion_coefficients)
    """
    focal_length = image_width if image_width > image_height else image_height
    center = (image_width / 2, image_height / 2)
    camera_matrix = np.array([[focal_length, 0, center[0]],
                             [0, focal_length, center[1]],
                             [0, 0, 1]], dtype="double")
    distortion_coeffs = np.zeros((4, 1))
    return camera_matrix, distortion_coeffs


class MarkerTracker:
    def __init__(self, marker_size=0.01, dictionary_id=cv2.aruco.DICT_4X4_100, calibration_file="camera_calibration.json", is_frame_undistorted=False, debug=False):
        """
        Initialize the marker tracker.
        
        Args:
            marker_size: Physical size of the markers in meters (useful for pose estimation)
            dictionary_id: ArUco dictionary to use for marker detection
            calibration_file: Path to the camera calibration file
            is_frame_undistorted: Whether frames passed to process_frame are already undistorted
            debug: Enable debug output
        """
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
        self.detector = cv2.aruco  # Use the aruco module directly for detecting markers
        self.marker_size = marker_size
        self.debug = debug
        self.is_frame_undistorted = is_frame_undistorted
        
        # Load camera calibration 
        self.camera_matrix, self.distortion_coeffs = load_camera_calibration(calibration_file, debug=debug)
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
        
        # Detect markers - if frames are already undistorted, pass None for distortion coeffs
        # This prevents double-correction of distortion
        detector_params = None  # Default parameters
        if self.is_frame_undistorted:
            # Frames are already undistorted, so don't apply distortion correction during detection
            self.corners, self.ids, _ = self.detector.detectMarkers(
                gray, self.aruco_dict, 
                parameters=detector_params,
                cameraMatrix=self.camera_matrix,
                distCoeff=None  # Don't apply distortion correction
            )
        else:
            # Apply distortion correction during detection
            self.corners, self.ids, _ = self.detector.detectMarkers(
                gray, self.aruco_dict, 
                parameters=detector_params,
                cameraMatrix=self.camera_matrix,
                distCoeff=self.distortion_coeffs
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
