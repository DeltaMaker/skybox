import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import mediapipe as mp
import cv2
from .geometry_utils import Point, draw_text

class HandTracker:
    def __init__(self, mode=False, maxHands=2, detectionCon=0.7,modelComplexity=1,trackCon=0.7,draw=True):
        self.mode = mode
        self.maxHands = maxHands
        self.detectionCon = detectionCon
        self.modelComplex = modelComplexity
        self.trackCon = trackCon
        self.draw = draw
        self.mpHands = mp.solutions.hands
        self.hands = self.mpHands.Hands(self.mode, self.maxHands,self.modelComplex,
                                        self.detectionCon, self.trackCon)
        self.mpDraw = mp.solutions.drawing_utils
        self.number_of_hands = 0
        self.multi_hand_landmarks = None
        self.feature_vector = None

    def process_frame(self, frame):
        imageRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(imageRGB)
        landmarks = results.multi_hand_landmarks if results else None
        self.number_of_hands = len(landmarks) if landmarks is not None else 0
        self.multi_hand_landmarks = landmarks
        
        # Create a serializable format of landmarks
        hands_data = []
        if landmarks:
            for hand_landmarks in landmarks:
                # Convert each landmark to a dict with x, y, z coordinates
                hand_points = []
                for landmark in hand_landmarks.landmark:
                    hand_points.append({
                        'x': round(landmark.x, 3),
                        'y': round(landmark.y, 3),
                        'z': round(landmark.z, 3)
                    })
                hands_data.append(hand_points)
        
        return hands_data
    

    def render_frame(self, frame, style=0):
        if self.draw:
            if style == 0 and self.number_of_hands > 0:
                for handLms in self.multi_hand_landmarks:
                    self.mpDraw.draw_landmarks(frame, handLms, self.mpHands.HAND_CONNECTIONS)
            else:
                for i in range(self.number_of_hands):
                    color = (0, 255, 255) if i == 0 else (255, 255, 0)
                    self.position_in_frame(frame, i, color, draw=True)
        return frame

    def landmark_list(self, hand_num=0):
        #return list(self.multi_hand_landmarks[hand_num].landmark) if self.number_of_hands > hand_num else []
        return self.landmarks_list[hand_num] if self.number_of_hands > hand_num else []
    def point_in_frame(self, frame, hand_num=0, landmark_num=0):
        point = None    # specified landmark (x,y) point in frame coordinates
        landmarks = self.landmark_list(hand_num)
        if landmarks:
            lm = landmarks[landmark_num]
            h, w, c = frame.shape
            point = Point( int(lm.x * w), int(lm.y * h) )
        return point

    def position_in_frame(self, frame, hand_num=0, color=(255,255,0), draw=False):
        pt_list = []    # landmark points in frame coordinates
        landmarks = self.landmark_list(hand_num)
        if landmarks:
            h, w, c = frame.shape
            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                pt_list.append( Point(cx,cy) )
                if draw:
                    cv2.circle(frame,(cx,cy), 3 , color, cv2.FILLED)
        return pt_list

