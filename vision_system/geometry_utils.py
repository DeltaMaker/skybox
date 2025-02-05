# geometry_utils.py

import cv2
import numpy as np
from dataclasses import dataclass
import math

@dataclass
class Point:
    x: float
    y: float

def calculate_slope(p1: Point, p2: Point) -> float:
    return None if p2.x == p1.x else (p2.y - p1.y) / (p2.x - p1.x)

def calculate_intercept(p: Point, slope: float) -> float:
    return p.x if slope is None else p.y - slope * p.x

def find_intersection_and_angle(p1: Point, p2: Point, p3: Point, p4: Point) -> tuple:
    m1, m2 = calculate_slope(p1, p2), calculate_slope(p3, p4)
    b1, b2 = calculate_intercept(p1, m1), calculate_intercept(p3, m2)

    if m1 == m2:
        return ("The lines are coincident.", None) if b1 == b2 else ("The lines are parallel and do not intersect.", None)

    x_intersect = p1.x if m1 is None else (p3.x if m2 is None else (b2 - b1) / (m1 - m2))
    y_intersect = (m2 * x_intersect + b2) if m1 is None else (m1 * x_intersect + b1)

    if m1 is None or m2 is None:
        angle = math.atan(abs(m2 if m1 is None else m1))
    elif m1 * m2 == -1:
        angle = math.pi / 2
    else:
        angle = math.atan(abs((m2 - m1) / (1 + m1 * m2)))

    return Point(x_intersect, y_intersect), math.degrees(angle)

def find_intersection(slope1: float, intercept1: float, slope2: float, intercept2: float) -> Point:
    if slope1 == slope2:
        return None
    if slope1 is None:
        return Point(intercept1, slope2 * intercept1 + intercept2)
    if slope2 is None:
        return Point(intercept2, slope1 * intercept2 + intercept1)
    x = (intercept2 - intercept1) / (slope1 - slope2)
    return Point(x, slope1 * x + intercept1)

def find_intersection_points(slope: float, intercept: float, width: int, height: int) -> list:
    points = []
    if slope is not None:
        y_left = intercept
        y_right = slope * width + intercept
        x_top = -intercept / slope if slope != 0 else 0
        x_bottom = (height - intercept) / slope if slope != 0 else 0

        if 0 <= y_left <= height:
            points.append((0, int(y_left)))
        if 0 <= y_right <= height:
            points.append((width, int(y_right)))
        if 0 <= x_top <= width and slope != 0:
            points.append((int(x_top), 0))
        if 0 <= x_bottom <= width and slope != 0:
            points.append((int(x_bottom), height))
    else:
        points.append((intercept, 0))
        points.append((intercept, height))
    return points

def calculate_angle_with_horizontal(slope: float) -> float:
    if slope is None:
        angle_deg = 90.0  # Vertical line
    else:
        angle_rad = math.atan(-slope)
        angle_deg = math.degrees(angle_rad)
    return angle_deg - 90 if angle_deg > 45 else angle_deg + 90 if angle_deg < -45 else angle_deg

def draw_line(image: np.ndarray, points: list, color: tuple = (0, 0, 255), thickness: int = 2) -> None:
    if len(points) >= 2:
        cv2.line(image, points[0], points[1], color, thickness)

def draw_circle(image: np.ndarray, point: Point, color: tuple = (255, 0, 0), radius: int = 12, thickness: int = 2) -> None:
    cv2.circle(image, (int(point.x), int(point.y)), radius, color, thickness)

def draw_text(image, text, point=Point(0.1,0.1), font_scale = 1.0, color=(255,255,255), thickness=2):
    if image is not None:
        text = str(text)
        height, width = image.shape[:2]
        position = (int(point.x * width), int(point.y * height))
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(image, text, position, font, font_scale, color, thickness)

def draw_crosshair_lines(image: np.ndarray, box_landmarks: tuple, color: tuple = (255, 0, 255), draw: bool = True) -> tuple:
    height, width = image.shape[:2]
    p1, p2, p3 = box_landmarks
    x1, y1 = int(p1.x * width), int(p1.y * height)
    x2, y2 = int(p2.x * width), int(p2.y * height)
    x3, y3 = int(p3.x * width), int(p3.y * height)

    main_slope = calculate_slope(Point(x1, y1), Point(x2, y2))
    main_intercept = calculate_intercept(Point(x1, y1), main_slope)
    main_points = find_intersection_points(main_slope, main_intercept, width, height)
    if draw:
        draw_line(image, main_points, color)

    perp_slope = -1 / main_slope if main_slope not in [None, 0] else 0 if main_slope is None else None
    perp_intercept = y3 - perp_slope * x3 if perp_slope is not None else y3 if main_slope == 0 else x3
    perp_points = find_intersection_points(perp_slope, perp_intercept, width, height)
    if draw:
        draw_line(image, perp_points, color)

    intersection = find_intersection(main_slope, main_intercept, perp_slope, perp_intercept)
    if intersection and draw:
        draw_circle(image, intersection, color)

    angle_with_horizontal = calculate_angle_with_horizontal(main_slope)

    return intersection, angle_with_horizontal

def calculate_angle_2d(a: Point, b: Point, c: Point) -> float:
    """Calculate the angle between three 2D points."""
    ba = np.array([a.x, a.y]) - np.array([b.x, b.y])
    bc = np.array([c.x, c.y]) - np.array([b.x, b.y])

    cos_angle = np.clip(np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc)), -1.0, 1.0)
    return round( np.degrees(np.arccos(cos_angle)) )

def calculate_angle_3d(a, b, c) -> float:
    """Calculate angle between three 3D points."""
    ba = np.array([a.x, a.y, a.z]) - np.array([b.x, b.y, b.z])
    bc = np.array([c.x, c.y, c.z]) - np.array([b.x, b.y, b.z])

    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
    cos_angle = np.clip(cos_angle, -1.0, 1.0)  # Ensure value is in the range [-1, 1]

    return round( np.degrees(np.arccos(cos_angle)) )

def bounding_box(points):
    """
    Calculate the bounding box for a list of points.

    Parameters:
    - points: List of Point instances.

    Returns:
    - A tuple containing two Point instances representing the top-left and bottom-right corners of the bounding box.
    """
    if not points:
        raise ValueError("The list of points is empty")
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    top_left = Point(min_x, min_y)
    bottom_right = Point(max_x, max_y)
    return (top_left, bottom_right)

def adjust_box(bounding_box, scale_factor):
    top_left, bottom_right = bounding_box
    # scale the box around it's center point
    cx, cy = (top_left.x + bottom_right.x) / 2, (top_left.y + bottom_right.y) / 2
    dx, dy = abs(top_left.x - bottom_right.x) / 2, abs(top_left.y - bottom_right.y) / 2
    top_left = Point(max(0, cx - dx * scale_factor), max(0, cy - dy * scale_factor))
    bottom_right = Point(min(1, cx + dx * scale_factor), min(1, cy + dy * scale_factor))
    return (top_left, bottom_right)

def extract_region(frame, bounding_box):
    top_left, bottom_right = bounding_box
    h, w, _ = frame.shape
    x1, y1 = int(top_left.x * w), int(top_left.y * h)
    x2, y2 = int(bottom_right.x * w), int(bottom_right.y * h)
    # Extract the region
    region = frame[y1:y2, x1:x2]
    return region

def convert_grayscale(img):
    # Example processing: Convert image to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return gray

def extract_contours(img):
    # Example: Extract contours (image data) without modifying the frame
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresholded = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresholded, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return contours

def draw_contours(img, contours):
    # Use extracted data (contours) to modify the frame
    if contours is not None:
        cv2.drawContours(img, contours, -1, (0, 255, 0), 2)
    return img

def main():
    # Example usage with Point objects
    p1, p2, p3 = Point(0.1, 0.1), Point(0.3, 0.9), Point(0.5, 0.5)
    image = np.ones((480, 640, 3), dtype=np.uint8) * 255

    intersection, angle = draw_crosshair_lines(image, (p1, p2, p3))

    print(f"Intersection Point: {intersection}")
    print(f"Angle with Horizontal: {angle} degrees")

    cv2.imshow('Lines', image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
