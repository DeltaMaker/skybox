import cv2
import numpy as np

class OverlayManager:

    def __init__(self):
        self.led_controller = None
        self.default_shape_values = {
            "circ": {"c": (0.1, 0.1), "r": 0.1, "col": (0, 255, 0), "th": -1},
            "rect": {"tl": (0.1, 0.1), "nbr": (0.1, 0.1), "w": 0.05, "h": 0.05, "col": (255, 0, 0), "th": 2},
            "text": {"pos": (0.1, 0.1), "txt": "Default Text", "scale": 1, "col": (255, 255, 255), "th": 2},
            "poly": {"points": [(0.6, 0.8), (0.7, 0.9), (0.8, 0.8), (0.7, 0.7), (0.7,0.9)], "col": (0, 255, 255), "closed": True, "th": 2}
        }

    def update_default_values(self, shape_key, shape):
        if shape_key in self.default_shape_values:
            for key, value in shape.items():
                print(f"  {key}: {value}")
                #if key != "type":
                self.default_shape_values[shape_key][key] = value
            #print(self.default_shape_values[shape_key])
            return self.default_shape_values[shape_key]
        else:
            return {}

    def scale_point(self, ratio_point, image_size):
        """Scale a ratio point (x, y) to actual pixel values based on image size."""
        return int(ratio_point[0] * image_size[0]), int(ratio_point[1] * image_size[1])

    # Function to draw shapes on the provided image
    def draw_overlay_shapes(self, frame, shapes):
        image_size = (frame.shape[1], frame.shape[0])  # Width, height of the image
        try:
            # Loop through the shapes list and draw them based on their type
            for shape in shapes:
                shape_key = shape.get("type", None)
                if shape_key is None:
                    continue
                values = self.update_default_values(shape_key, shape)
                if shape_key == "circ":  # Circle
                    center = self.scale_point(shape["c"], image_size)
                    radius = int(values["r"] * min(image_size))  # Scale radius relative to the smaller dimension
                    cv2.circle(frame, center, radius, tuple(values["col"]), thickness=values["th"])
                elif shape_key == "rect":  # Rectangle
                    top_left = self.scale_point(values["tl"], image_size)
                    if "br" in values:
                        bottom_right = self.scale_point(values["br"], image_size)
                    else:
                        bottom_right = self.scale_point((values["tl"][0]+values["w"],values["tl"][1]+values["h"]), image_size)
                    #print(f"bottom_right = {bottom_right}")
                    cv2.rectangle(frame, top_left, bottom_right, tuple(values["col"]), thickness=values["th"])
                elif shape_key == "poly":  # Polyline
                    points = [self.scale_point(p, image_size) for p in values["points"]]
                    points = np.array(points, np.int32).reshape((-1, 1, 2))
                    cv2.polylines(frame, [points], isClosed=values["closed"], color=tuple(values["col"]),
                                  thickness=values["th"])
                elif shape_key == "text":  # Text
                    text_position = self.scale_point(values["pos"], image_size)
                    font = cv2.FONT_HERSHEY_SIMPLEX  # Default font (you can customize this)
                    cv2.putText(frame, values["txt"], text_position, font, values["scale"], tuple(values["col"]),
                                thickness=values["th"], lineType=cv2.LINE_AA)
        except Exception as e:
            print(f'Exception in draw_overlay_shapes(): {e}')

        return frame

