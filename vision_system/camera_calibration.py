"""
Camera Calibration Script
=========================

This script performs camera calibration using OpenCV and a checkerboard pattern.
It saves the resulting camera matrix and distortion coefficients to a file,
which can then be used by the marker tracking system for more accurate marker detection.

Usage:
    python camera_calibration.py [--camera CAMERA_ID] [--images NUM_IMAGES] 
                                [--output CALIBRATION_FILE] [--debug]

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
"""

import os
import sys
import time
import json
import argparse
import numpy as np
import cv2


class CameraCalibrator:
    def __init__(self, camera_id=0, board_size=(9, 6), square_size=20.0, debug=False):
        """
        Initialize the camera calibrator.
        
        Args:
            camera_id: Camera device ID for OpenCV
            board_size: Tuple of (columns, rows) of internal corners in the checkerboard
            square_size: Size of checkerboard squares in mm (not critical for ArUco tracking)
            debug: Enable debug output
        """
        self.camera_id = camera_id
        self.board_size = board_size
        self.square_size = square_size
        self.debug = debug
        
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
    
    def capture_calibration_frames(self, num_images=20, delay_seconds=2):
        """
        Capture multiple frames showing the checkerboard pattern.
        
        Args:
            num_images: Number of images to capture for calibration
            delay_seconds: Delay between captures in seconds
        
        Returns:
            True if enough images were captured, False otherwise
        """
        if self.cap is None:
            self.initialize_camera()
        
        captured = 0
        last_capture_time = 0
        
        print("\nStarting calibration capture...")
        print("Position the checkerboard in different orientations.")
        print(f"Will capture {num_images} images with {delay_seconds}s delay between each.\n")
        
        while captured < num_images:
            ret, frame = self.cap.read()
            if not ret:
                print("Failed to read frame")
                continue
            
            # Make a copy for drawing
            display_frame = frame.copy()
            
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Find the chessboard corners
            ret, corners = cv2.findChessboardCorners(gray, self.board_size, None)
            
            # If found, add object points and image points
            current_time = time.time()
            time_to_next = max(0, delay_seconds - (current_time - last_capture_time))
            
            if ret:
                # Draw corners on the display frame
                cv2.drawChessboardCorners(display_frame, self.board_size, corners, ret)
                
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
            
            # Show instructions
            cv2.putText(display_frame, "Position checkerboard in view", 
                       (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            
            # Display the resulting frame
            cv2.imshow('Camera Calibration', display_frame)
            
            # Break loop on ESC key
            if cv2.waitKey(1) & 0xFF == 27:
                break
        
        self.cap.release()
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
            "calibration_date": time.strftime("%Y-%m-%d %H:%M:%S")
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
            if self.cap and self.cap.isOpened():
                self.cap.release()
            cv2.destroyAllWindows()


def main():
    """Run the camera calibration with command line arguments."""
    parser = argparse.ArgumentParser(description="Camera Calibration Tool")
    parser.add_argument("--camera", type=int, default=0,
                      help="Camera device ID (default: 0)")
    parser.add_argument("--images", type=int, default=20,
                      help="Number of images to capture (default: 20)")
    parser.add_argument("--output", type=str, default="camera_calibration.json",
                      help="Output file path (default: camera_calibration.json)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    args = parser.parse_args()
    
    # Use 6x9 for a 7x10 checkerboard (internal corners)
    calibrator = CameraCalibrator(camera_id=args.camera, board_size=(9, 6), debug=args.debug)
    
    success = calibrator.run_calibration(num_images=args.images, output_file=args.output)
    
    if success:
        print("\nCalibration completed successfully.")
        print("Use this calibration file with the marker tracking system for improved accuracy.")
    else:
        print("\nCalibration failed or was incomplete.")
        print("Please try again, ensuring the checkerboard is clearly visible.")


if __name__ == "__main__":
    main() 