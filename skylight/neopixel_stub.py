#import cv2
#import numpy as np

class NeoPixel:
    def __init__(self, pin, n, brightness=1.0, auto_write=True, pixel_order=None):
        self.n = n
        self.pixels = [(0, 0, 0)] * n
        self.brightness = brightness
        self.pixel_order = pixel_order
        self.debug = True
        self.disp_pix = ""
        print(f"Initialized mock NeoPixel strip on pin {pin} with {n} pixels, pixel order: {pixel_order}, debug: {self.debug}")

    def __del__(self):
        #cv2.destroyAllWindows()
        pass

    def draw_neopixel_strip(self, frame, radius=10, margin=2):
        """Draw a NeoPixel strip at the bottom of the frame."""
        y_position = frame.shape[0] - (radius + margin)  # Y position of the strip
        for i in range(self.n):
            x_position = (frame.shape[1] // self.n) * i + radius
            color = self.pixels[i]  # Color of the pixel
            cv_color = (int(color[2]), int(color[1]), int(color[0]))  # Convert RGB to BGR for OpenCV
            if sum(cv_color) > 0:  # don't draw if black
                cv2.circle(frame, (x_position, y_position), radius, cv_color, -1)
        return frame

    def __setitem__(self, index, val):
        if index < len(self.pixels):
            self.pixels[index] = val

    def show(self, height = 20, width = 400):
        #image = np.ones((height, width, 3), np.uint8) * 255
        #image = self.draw_neopixel_strip(image)
        #cv2.imshow('Neopixels', image)

        pix = ""
        for p in self.pixels[:15]:
            #pix += '#%02x%02x%02x ' % p
            pix += f'({p[0]},{p[1]},{p[2]})'
        if self.debug and pix != self.disp_pix:
            #print (pix)
            self.disp_pix = pix

    def fill(self, color):
        for i in range(self.n):
            self.__setitem__(i, color)

# Common pixel order constants
RGB = 'RGB'
GRB = 'GRB'
RGBW = 'RGBW'
GRBW = 'GRBW'

