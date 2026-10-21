"""
detection/detection_types.py
-------------------------------
Plain data types shared by the detection/tracking/analysis layers.
Kept dependency-free (no cv2/ultralytics) so other modules (e.g. the
tracker or unit tests) can use `Detection` without pulling in YOLO.
"""

from dataclasses import dataclass


@dataclass
class Detection:
    """A single detected object in a frame."""
    class_id: int
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def bbox(self):
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
