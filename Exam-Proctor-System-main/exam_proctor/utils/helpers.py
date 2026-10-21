# """
# utils/helpers.py
# ------------------
# Small reusable helpers used across modules: drawing bounding boxes,
# saving evidence screenshots with consistent naming, and formatting.
# """

# import os
# import time
# import cv2

# from config.config import Config

# COLOR_NORMAL = (60, 180, 75)      # green (BGR)
# COLOR_FLAGGED = (0, 0, 220)       # red (BGR)
# COLOR_PHONE = (0, 165, 255)       # orange (BGR)


# def draw_student_box(frame, bbox, track_id: int, score: float, flagged: bool):
#     """Draw a labeled bounding box for a tracked student on the frame."""
#     x1, y1, x2, y2 = bbox
#     color = COLOR_FLAGGED if flagged else COLOR_NORMAL
#     cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
#     label = f"ID {track_id} | score {score:.0f}"
#     (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
#     cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
#     cv2.putText(frame, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
#     return frame


# def draw_phone_box(frame, bbox):
#     x1, y1, x2, y2 = bbox
#     cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_PHONE, 2)
#     cv2.putText(frame, "phone", (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_PHONE, 1)
#     return frame


# def save_screenshot(frame, exam_id: int, track_id: int, incident_type: str) -> str:
#     """Save a JPEG evidence screenshot, return the path stored relative to /static."""
#     Config.ensure_directories()
#     timestamp = time.strftime("%Y%m%d_%H%M%S")
#     filename = f"exam{exam_id}_track{track_id}_{incident_type}_{timestamp}.jpg"
#     abs_path = os.path.join(Config.SCREENSHOT_DIR, filename)
#     cv2.imwrite(abs_path, frame)
#     return os.path.join("screenshots", filename)  # relative to /static for url_for


# def frame_to_jpeg_bytes(frame) -> bytes:
#     """Encode a frame as JPEG bytes for MJPEG streaming."""
#     ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
#     return buffer.tobytes() if ok else b""


"""
utils/helpers.py
------------------
Small reusable helpers used across modules: drawing bounding boxes,
saving evidence screenshots with consistent naming, and formatting.
"""

import os
import time
import cv2

from config.config import Config

COLOR_ALERT = (0, 0, 255)       # Đỏ: Cảnh báo vi phạm (BGR)
COLOR_PAPER = (255, 0, 0)       # Xanh dương: Phao thi (cheat_paper)
COLOR_OBJECT = (255, 165, 0)     # Cam: Thiết bị điện tử khác (Phone/Laptop)


def draw_student_box(frame, bbox, track_id: int, incident_type: str = None):
    """
    Chỉ vẽ Bounding Box cho thí sinh KHI CÓ CẢNH BÁO (Giống ảnh 2).
    Nếu incident_type là None -> Học sinh bình thường, KHÔNG VẼ KHUNG.
    """
    if not incident_type:
        return frame

    x1, y1, x2, y2 = map(int, bbox)
    
    # 1. Vẽ ô màu đỏ bọc thí sinh vi phạm
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_ALERT, 2)
    
    # 2. In nhãn CẢNH BÁO màu đỏ phía trên khung (Ví dụ: CANH BAO: QUAY DAU)
    label = f"CANH BAO: {incident_type.upper()}"
    cv2.putText(
        frame, 
        label, 
        (x1, max(15, y1 - 10)), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.6, 
        COLOR_ALERT, 
        2, 
        cv2.LINE_AA
    )
    return frame


def draw_custom_object_box(frame, bbox, label: str, confidence: float):
    """
    Vẽ khung bọc phao thi (cheat_paper) hoặc điện thoại/laptop (Chuẩn ảnh 2).
    """
    x1, y1, x2, y2 = map(int, bbox)
    
    # Chọn màu: Phao thi màu xanh dương, đồ dùng khác màu cam
    color = COLOR_PAPER if "paper" in label.lower() else COLOR_OBJECT
    
    # 1. Vẽ khung vuông nhỏ bọc đúng vật thể
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    
    # 2. In tên vật thể + điểm tin cậy (Ví dụ: cheat_paper 0.88)
    tag = f"{label} {confidence:.2f}"
    cv2.putText(
        frame, 
        tag, 
        (x1, max(15, y1 - 8)), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        0.55, 
        color, 
        2, 
        cv2.LINE_AA
    )
    return frame


def save_screenshot(frame, exam_id: int, track_id: int, incident_type: str) -> str:
    """Save a JPEG evidence screenshot, return the path stored relative to /static."""
    Config.ensure_directories()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"exam{exam_id}_track{track_id}_{incident_type}_{timestamp}.jpg"
    abs_path = os.path.join(Config.SCREENSHOT_DIR, filename)
    cv2.imwrite(abs_path, frame)
    return os.path.join("screenshots", filename)  # relative to /static for url_for


def frame_to_jpeg_bytes(frame) -> bytes:
    """Encode a frame as JPEG bytes for MJPEG streaming."""
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buffer.tobytes() if ok else b""