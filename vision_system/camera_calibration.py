"""
Camera Calibration Script
=========================

This script performs camera calibration using OpenCV and a checkerboard pattern.
It saves the resulting camera matrix and distortion coefficients to a file,
which can then be used by the marker tracking system for more accurate marker detection.

Usage:
    python camera_calibration.py [--camera CAMERA_ID] [--url SNAPSHOT_URL] [--images NUM_IMAGES] 
                                [--output CALIBRATION_FILE] [--debug] [--headless]

Instructions:
    1. Print a 7x10 checkerboard pattern (internal corners: 6x9)
    2. Mount the pattern on a rigid surface
    3. Run this script
    4. Move the checkerboard slowly to different positions and angles
    5. The script will capture multiple images and perform calibration
    6. Results will be saved to the specified output file

Dependencies:
    - OpenCV (cv2)
    - NumPy
    - Requests (for URL snapshot mode)
"""

import os
import sys
import time
import json
import argparse
import numpy as np
import cv2
import requests


class CameraCalibrator:
    def __init__(self, camera_id=0, snapshot_url=None, board_size=(9, 6), square_size=20.0, debug=False, headless=False):
        """
        Initialize the camera calibrator.
        
        Args:
            camera_id: Camera device ID for OpenCV (ignored if snapshot_url is provided)
            snapshot_url: URL for fetching camera snapshots (e.g., http://localhost/webcam/?action=snapshot)
            board_size: Tuple of (columns, rows) of internal corners in the checkerboard
            square_size: Size of checkerboard squares in mm (not critical for ArUco tracking)
            debug: Enable debug output
            headless: Run without GUI display
        """
        self.camera_id = camera_id
        self.snapshot_url = snapshot_url
        self.board_size = board_size
        self.square_size = square_size
        self.debug = debug
        self.headless = headless
        self.use_url = snapshot_url is not None
        
        # Prepare object points (0,0,0), (1,0,0), (2,0,0) ... (8,5,0)
        self.objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2) * square_size
        
        # Arrays to store object points and image points
        self.objpoints = []  # 3D points in real world space
        self.imgpoints = []  # 2D points in image plane
        
        self.cap = None
        self.image_size = None
        
    def initialize_camera(self):
        """Initialize the camera capture."""
        if self.use_url:
            # Try to get an initial image to determine resolution
            try:
                initial_frame = self.get_frame_from_url()
                if initial_frame is not None:
                    height, width = initial_frame.shape[:2]
                    self.image_size = (width, height)
                    if self.debug:
                        print(f"URL camera initialized with resolution: {width}x{height}")
                    return
            except Exception as e:
                raise ValueError(f"Failed to initialize from URL {self.snapshot_url}: {e}")
        else:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                raise ValueError(f"Failed to open camera {self.camera_id}")
            
            # Set resolution to HD if possible
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Get the actual camera resolution
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.image_size = (width, height)
            
            if self.debug:
                print(f"Camera initialized with resolution: {width}x{height}")
    
    def get_frame_from_url(self):
        """Fetch a frame from the snapshot URL."""
        try:
            response = requests.get(self.snapshot_url, timeout=5.0)
            if response.status_code != 200:
                print(f"Error fetching image from URL: HTTP {response.status_code}")
                return None
                
            # Convert to OpenCV format
            image_array = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if frame is None:
                print("Failed to decode image from URL")
            
            return frame
        except Exception as e:
            print(f"Error fetching image from URL: {e}")
            return None
    
    def get_frame(self):
        """Get a frame from either the camera or URL."""
        if self.use_url:
            return self.get_frame_from_url()
        else:
            if self.cap is None or not self.cap.isOpened():
                self.initialize_camera()
            ret, frame = self.cap.read()
            return frame if ret else None
    
    def capture_calibration_frames(self, num_images=20, delay_seconds=2):
        """
        Capture multiple frames showing the checkerboard pattern.
        
        Args:
            num_images: Number of images to capture for calibration
            delay_seconds: Delay between captures in seconds
        
        Returns:
            True if enough images were captured, False otherwise
        """
        if self.image_size is None:
            self.initialize_camera()
        
        captured = 0
        last_capture_time = 0
        
        print("\nStarting calibration capture...")
        print("Position the checkerboard in different orientations.")
        print(f"Will capture {num_images} images with {delay_seconds}s delay between each.\n")
        
        if self.headless:
            print("Running in headless mode.")
            print("Press ENTER to capture an image when the checkerboard is in position.")
            print("Press Ctrl+C at any time to cancel.")
        
        try:
            while captured < num_images:
                frame = self.get_frame()
                if frame is None:
                    print("Failed to read frame")
                    time.sleep(0.5)  # Small delay to prevent rapid error messages
                    continue
                
                # Make a copy for drawing
                display_frame = frame.copy()
                
                # Convert to grayscale
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Find the chessboard corners
                ret, corners = cv2.findChessboardCorners(gray, self.board_size, None)
                
                # If found, draw corners on display frame
                if ret:
                    # Draw corners on the display frame if not headless
                    if not self.headless:
                        cv2.drawChessboardCorners(display_frame, self.board_size, corners, ret)
                    
                    current_time = time.time()
                    time_to_next = max(0, delay_seconds - (current_time - last_capture_time))
                    
                    # In headless mode, wait for user input to capture
                    if self.headless:
                        if ret:
                            print(f"Checkerboard detected! Press ENTER to capture, or 'q' then ENTER to quit.")
                            user_input = input().strip().lower()
                            if user_input == 'q':
                                print("Capture cancelled by user.")
                                break
                                
                            # Capture the image
                            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), 
                                                      (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
                            
                            self.objpoints.append(self.objp)
                            self.imgpoints.append(corners2)
                            
                            captured += 1
                            last_capture_time = current_time
                            
                            print(f"Captured image {captured}/{num_images}")
                            print(f"Position checkerboard differently and press ENTER for next capture.")
                        else:
                            print("No checkerboard detected. Reposition and try again.")
                            time.sleep(1)
                    else:
                        # GUI mode handling
                        # Display countdown if we're waiting to capture
                        if time_to_next > 0:
                            # Show countdown
                            cv2.putText(display_frame, f"Next capture in: {time_to_next:.1f}s", 
                                      (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        elif captured < num_images:
                            # Refine corners for better accuracy
                            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), 
                                                      (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
                            
                            self.objpoints.append(self.objp)
                            self.imgpoints.append(corners2)
                            
                            captured += 1
                            last_capture_time = current_time
                            
                            # Show confirmation text
                            cv2.putText(display_frame, f"Captured {captured}/{num_images}", 
                                      (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                            print(f"Captured image {captured}/{num_images}")
                
                # In GUI mode, show frames and check for ESC key
                if not self.headless:
                    # Show instructions
                    cv2.putText(display_frame, "Position checkerboard in view", 
                              (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                    
                    # Display the resulting frame
                    cv2.imshow('Camera Calibration', display_frame)
                    
                    # Break loop on ESC key
                    if cv2.waitKey(1) & 0xFF == 27:
                        break
                else:
                    # In headless mode, just wait a bit
                    if not ret:
                        time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nCalibration interrupted by user.")
        finally:
            # Clean up
            if not self.use_url and self.cap is not None:
                self.cap.release()
            if not self.headless:
                cv2.destroyAllWindows()
        
        print(f"\nCapture complete. Collected {captured}/{num_images} images.")
        return captured >= 5  # Need at least 5 images for a decent calibration
    
    def calibrate(self):
        """
        Perform the calibration calculation.
        
        Returns:
            Tuple of (camera_matrix, distortion_coefficients) or None if calibration failed
        """
        if not self.imgpoints:
            print("No calibration data collected!")
            return None
        
        print("\nPerforming calibration calculations...")
        
        ret, camera_matrix, distortion_coeffs, rvecs, tvecs = cv2.calibrateCamera(
            self.objpoints, self.imgpoints, (self.image_size[1], self.image_size[0]), None, None)
        
        if not ret:
            print("Calibration failed!")
            return None
        
        # Calculate reprojection error as quality metric
        mean_error = 0
        for i in range(len(self.objpoints)):
            imgpoints2, _ = cv2.projectPoints(self.objpoints[i], rvecs[i], tvecs[i], 
                                             camera_matrix, distortion_coeffs)
            error = cv2.norm(self.imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
            mean_error += error
        
        print(f"Calibration successful!")
        print(f"Average reprojection error: {mean_error/len(self.objpoints)}")
        
        return camera_matrix, distortion_coeffs
    
    def save_calibration(self, camera_matrix, distortion_coeffs, output_file):
        """
        Save the calibration results to a file.
        
        Args:
            camera_matrix: The calculated camera matrix
            distortion_coeffs: The calculated distortion coefficients
            output_file: Path to the output file
        
        Returns:
            True if successful, False otherwise
        """
        # Convert numpy arrays to lists for JSON serialization
        calibration_data = {
            "camera_matrix": camera_matrix.tolist(),
            "distortion_coefficients": distortion_coeffs.tolist(),
            "image_size": self.image_size,
            "calibration_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": self.snapshot_url if self.use_url else f"camera_id_{self.camera_id}"
        }
        
        try:
            with open(output_file, 'w') as f:
                json.dump(calibration_data, f, indent=4)
            print(f"Calibration data saved to {output_file}")
            return True
        except Exception as e:
            print(f"Error saving calibration data: {e}")
            return False
    
    def run_calibration(self, num_images=20, output_file="camera_calibration.json"):
        """
        Run the full calibration process.
        
        Args:
            num_images: Number of images to capture
            output_file: Path to the output file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.capture_calibration_frames(num_images):
                results = self.calibrate()
                if results:
                    camera_matrix, distortion_coeffs = results
                    return self.save_calibration(camera_matrix, distortion_coeffs, output_file)
            return False
        finally:
            if not self.use_url and self.cap and self.cap.isOpened():
                self.cap.release()
            if not self.headless:
                cv2.destroyAllWindows()


def main():
    """Run the camera calibration with command line arguments."""
    parser = argparse.ArgumentParser(description="Camera Calibration Tool")
    parser.add_argument("--camera", type=int, default=0,
                      help="Camera device ID (default: 0)")
    parser.add_argument("--url", type=str, default=None,
                      help="URL for snapshot images (e.g., http://localhost/webcam/?action=snapshot)")
    parser.add_argument("--images", type=int, default=20,
                      help="Number of images to capture (default: 20)")
    parser.add_argument("--output", type=str, default="camera_calibration.json",
                      help="Output file path (default: camera_calibration.json)")
    parser.add_argument("--square-size", type=float, default=20.0,
                      help="Size of checkerboard squares in mm (default: 20.0)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    parser.add_argument("--headless", action="store_true",
                      help="Run in headless mode without GUI windows")
    args = parser.parse_args()
    
    # Use 6x9 for a 7x10 checkerboard (internal corners)
    calibrator = CameraCalibrator(
        camera_id=args.camera,
        snapshot_url=args.url,
        board_size=(9, 6),
        square_size=args.square_size,
        debug=args.debug,
        headless=args.headless
    )
    
    success = calibrator.run_calibration(num_images=args.images, output_file=args.output)
    
    if success:
        print("\nCalibration completed successfully.")
        print("Use this calibration file with the marker tracking system for improved accuracy.")
    else:
        print("\nCalibration failed or was incomplete.")
        print("Please try again, ensuring the checkerboard is clearly visible.")


if __name__ == "__main__":
    main() 