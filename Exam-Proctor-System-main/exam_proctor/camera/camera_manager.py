"""
camera/camera_manager.py
------------------------
Handles reading frames from either a hardware webcam index (int/str '0')
or a video file path using OpenCV.
"""

import os
import cv2
from config.config import Config


class CameraManager:
    """Encapsulates OpenCV video capture stream."""

    def __init__(self, source=None):
        raw_source = source if source is not None else Config.DEFAULT_CAMERA_SOURCE
        self.source = raw_source
        self.cap = None

    def open(self) -> bool:  # <--- Đã thêm self
        """Initialize the video stream. Returns True if successfully opened."""
        source_str = str(self.source).strip()

        # Kiểm tra nếu là webcam index (ví dụ: '0', '1', 0)
        if source_str.isdigit():
            index = int(source_str)
            if index == 0:
                target_source = index
            elif index == 1:
                target_source = "http://192.168.31.117:8081"
            else:
                target_source = index
        else:
            # Nếu là file video, tự động chuyển về đường dẫn tuyệt đối
            if not os.path.isabs(source_str):
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                possible_path = os.path.join(project_root, source_str)
                if os.path.exists(possible_path):
                    target_source = possible_path
                else:
                    # Kiểm tra trong thư mục uploads hoặc root nếu người dùng chỉ nhập tên file
                    target_source = os.path.join(project_root, "uploads", source_str)
                    if not os.path.exists(target_source):
                        target_source = source_str
            else:
                target_source = source_str

        print(f"[CameraManager] Attempting to open video source: {target_source}")
        self.cap = cv2.VideoCapture(target_source)

        if not self.cap.isOpened():
            print(f"[CameraManager] ERROR: Could not open video source: {target_source}")
            return False

        print(f"[CameraManager] Successfully opened video source: {target_source}")
        return True

    def read(self):  # <--- Đã thêm self
        """
        Read the next frame from the camera/video.
        Returns (success: bool, frame: np.ndarray or None).
        If playing a video file and it reaches the end, loops back to frame 0.
        """
        if self.cap is None or not self.cap.isOpened():
            return False, None

        ret, frame = self.cap.read()
        
        # Tự động loop lại từ đầu nếu file video chạy hết khung hình
        if not ret and not str(self.source).strip().isdigit():
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()

        return ret, frame

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def is_opened(self) -> bool:  # <--- Đã thêm self
        return self.cap is not None and self.cap.isOpened()