import cv2
import numpy as np
import os
def generate_aruco_board(
    marker_ids,           # List of marker IDs to include
    output_file,         # Output filename
    marker_size_mm=10,   # Size of each marker in millimeters
    margin_size_mm=4,    # Margin size between markers in millimeters
    dpi=300,            # Dots per inch for printing
    #dictionary_id=cv2.aruco.DICT_5X5_250,
    dictionary_id=cv2.aruco.DICT_4X4_100,
    dir_path="vision_system/markers"
):
    """Generate an ArUco marker board with specific marker IDs."""
    
    # Convert mm to pixels
    MM_TO_INCH = 1/25.4  # 1 inch = 25.4 mm
    pixels_per_mm = dpi * MM_TO_INCH
    
    # Calculate sizes in pixels
    marker_size_px = int(marker_size_mm * pixels_per_mm)
    margin_size_px = int(margin_size_mm * pixels_per_mm)
    
    # Create the dictionary
    aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_id)
    
    # Calculate the board size in pixels based on number of markers
    markers_x = len(marker_ids)  # Place markers horizontally
    markers_y = 1
    board_width_px = int(markers_x * (marker_size_mm + margin_size_mm) * pixels_per_mm + margin_size_px)
    board_height_px = int(markers_y * (marker_size_mm + margin_size_mm) * pixels_per_mm + margin_size_px)
    
    # Create a white background
    board = np.ones((board_height_px, board_width_px), dtype=np.uint8) * 255
    
    # Generate and place each marker
    for x, marker_id in enumerate(marker_ids):
        # Calculate marker position in pixels
        x_pos = int(margin_size_mm * pixels_per_mm + x * (marker_size_mm + margin_size_mm) * pixels_per_mm)
        y_pos = int(margin_size_mm * pixels_per_mm)
        
        # Generate the marker
        marker = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_size_px)
        # Place the marker on the board
        board[y_pos:y_pos+marker_size_px, x_pos:x_pos+marker_size_px] = marker
        # Add the marker ID to the board
        id_text = f"{marker_id}"
        # Add size information to the image
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.75
        text_color = 0  # Black
        cv2.putText(board, id_text, (x_pos, y_pos-margin_size_px//2), 
                font, font_scale, text_color, 1, cv2.LINE_AA)
    
    # Add size information to the image
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.75
    text_color = 0  # Black
    info_text = f"Marker size: {marker_size_mm}mm x {marker_size_mm}mm @ {dpi} DPI"
    id_text = f"Marker IDs: {marker_ids}"
    #cv2.putText(board, info_text, (margin_size_px, board_height_px - margin_size_px), 
    #            font, font_scale, text_color, 1, cv2.LINE_AA)
    #cv2.putText(board, id_text, (margin_size_px, board_height_px - 2*margin_size_px), 
    #            font, font_scale, text_color, 1, cv2.LINE_AA)
    
    # Save the board
    os.makedirs(dir_path, exist_ok=True)
    output_file = os.path.join(dir_path, output_file)
    cv2.imwrite(output_file, board)
    print(f"Generated board with {len(marker_ids)} markers")
    print(f"Marker IDs: {marker_ids}")
    print(f"Saved to: {output_file}")
    
    return board

def generate_marker_sets(marker_sets):
    """Generate multiple marker boards from a list of specifications."""
    for marker_set in marker_sets:
        generate_aruco_board(
            marker_ids=marker_set['ids'],
            output_file=marker_set['file'],
            marker_size_mm=10,
            margin_size_mm=3,
            dpi=300
        )

# Example usage
if __name__ == "__main__":
    # Define the marker sets
    dock_sets = [
        {'file': 'dock11.png', 'ids': [51, 11]},
        {'file': 'dock12.png', 'ids': [51, 12]},
        {'file': 'dock21.png', 'ids': [52, 21]},
        {'file': 'dock22.png', 'ids': [52, 22]},
        {'file': 'dock31.png', 'ids': [53, 31]},
        {'file': 'dock32.png', 'ids': [53, 32]},
    ]
    tool_sets = [
        {'file': 'tool0.png', 'ids': [10, 41]},
        {'file': 'tool1.png', 'ids': [1, 41]},
        {'file': 'tool2.png', 'ids': [2, 42]},
        {'file': 'tool3.png', 'ids': [3, 42]},
        {'file': 'tool4.png', 'ids': [4, 43]},
        {'file': 'tool5.png', 'ids': [5, 43]},
    ]

    test_sets = [
        {'file': 'test0.png', 'ids': [0, 2, 3, 4, 5, 6, 7, 9]},
        {'file': 'test1.png', 'ids': [10, 20, 30, 40, 50, 60, 70, 80]},
        {'file': 'test2.png', 'ids': [11, 12, 13, 14, 15, 16, 17, 18]},
        {'file': 'test3.png', 'ids': [91, 92, 93, 94, 95, 96, 97, 98]},
    ]
    id_sets = [
        {'file': 'id0.png', 'ids': [81, 82, 83, 84]},
        {'file': 'id1.png', 'ids': [85, 86, 87, 88]},
        {'file': 'id2.png', 'ids': [91, 92, 93, 94]},
        {'file': 'id3.png', 'ids': [95, 96, 97, 98]},
    ]

    marker_sets = dock_sets + tool_sets + test_sets + id_sets
    # Generate all marker sets
    generate_marker_sets(id_sets)
