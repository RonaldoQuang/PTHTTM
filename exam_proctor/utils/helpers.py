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
import unicodedata
import cv2
import numpy as np
from datetime import datetime, timezone, timedelta

from config.config import Config

# --- Nhãn tiếng Việt để hiển thị trên giao diện web ---
INCIDENT_LABELS = {
    # loại sự cố từ hệ thống cũ
    "looking_away": "Quay đầu nhìn quanh",
    "mobile_phone": "Dùng điện thoại",
    "standing": "Đứng dậy",
    "left_seat": "Rời chỗ ngồi",
    "object_passing": "Chuyền đồ vật",
    "face_not_visible": "Không thấy khuôn mặt",
    "close_interaction": "Trao đổi sát nhau",
    # loại sự cố từ MonitoringService (ensemble)
    "quay_dau": "Quay đầu",
    "cui_gam_mat": "Cúi gằm mặt",
    "cui_dau_thap": "Cúi đầu thấp",
    "gio_tay_cao": "Giơ tay cao",
    "nam_ra_ban": "Nằm ra bàn",
    "dung_day": "Đứng dậy",
    "cheat_paper": "Phao thi / tài liệu",
    "laptop": "Dùng laptop",
}

# Mức độ để tô màu nhãn sự cố trên giao diện: danger (đỏ) / warning (vàng) / info (xanh)
INCIDENT_SEVERITY = {
    "dung_day": "danger", "nam_ra_ban": "danger", "standing": "danger", "left_seat": "danger",
    "mobile_phone": "danger", "object_passing": "danger", "cheat_paper": "danger", "laptop": "danger",
    "quay_dau": "warning", "gio_tay_cao": "warning", "looking_away": "warning", "close_interaction": "warning",
    "cui_gam_mat": "info", "cui_dau_thap": "info", "face_not_visible": "info",
}

STATUS_LABELS = {
    "scheduled": "Đã lên lịch",
    "running": "Đang giám sát",
    "completed": "Đã hoàn thành",
    "flagged": "Bị gắn cờ",
    "active": "Đang theo dõi",
    "left": "Đã rời đi",
}

# --- Font hỗ trợ tiếng Việt (có sẵn trên Windows / macOS / Linux) ---
_FONT_FAMILIES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeuii.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf", None),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"),
]


def find_unicode_font():
    """Trả về {'regular','bold','italic'} (đường dẫn .ttf) hoặc None nếu máy không có font phù hợp."""
    for regular, bold, italic in _FONT_FAMILIES:
        if os.path.exists(regular):
            return {
                "regular": regular,
                "bold": bold if bold and os.path.exists(bold) else regular,
                "italic": italic if italic and os.path.exists(italic) else regular,
            }
    return None


def fold_vietnamese(text) -> str:
    """Bỏ dấu tiếng Việt (dùng khi không tìm thấy font Unicode)."""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


_font_cache = {}


def _get_pil_font(size):
    if size not in _font_cache:
        from PIL import ImageFont
        fonts = find_unicode_font()
        try:
            _font_cache[size] = ImageFont.truetype(fonts["bold"], size) if fonts else None
        except Exception:
            _font_cache[size] = None
    return _font_cache[size]


def draw_texts_vi(img, items):
    """Vẽ chữ tiếng Việt CÓ DẤU lên ảnh BGR (cv2.putText không vẽ được dấu).
    items: [(text, (x, y_baseline), (b, g, r), size)]. Vẽ trực tiếp vào img."""
    if not items:
        return
    try:
        from PIL import Image, ImageDraw
        fonts = {size: _get_pil_font(size) for size in {it[3] for it in items}}
        if any(f is None for f in fonts.values()):
            raise RuntimeError("no unicode font")
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        for text, (x, y), (b, g, r), size in items:
            draw.text((x, y), text, font=fonts[size], fill=(r, g, b), anchor="ls",
                      stroke_width=1, stroke_fill=(0, 0, 0))
        img[:] = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        # Không có font/Pillow: vẽ không dấu để chương trình vẫn chạy
        for text, (x, y), color, size in items:
            cv2.putText(img, fold_vietnamese(text), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                        size / 30.0, color, 2, cv2.LINE_AA)

VN_TZ = timezone(timedelta(hours=7))


def incident_label(value) -> str:
    text = str(value or "")
    key = text.strip().lower().replace(" ", "_")
    return INCIDENT_LABELS.get(key, text.replace("_", " "))


def incident_severity(value) -> str:
    key = str(value or "").strip().lower().replace(" ", "_")
    return INCIDENT_SEVERITY.get(key, "secondary")


def status_label(value) -> str:
    text = str(value or "")
    return STATUS_LABELS.get(text.strip().lower(), text)


def vn_datetime(value) -> str:
    """'2026-10-27 15:04:52' (UTC trong SQLite) -> '27/10/2026 22:04:52' (giờ Việt Nam).
    Chuỗi chỉ có ngày '2026-10-27' -> '27/10/2026'."""
    if not value:
        return ""
    text = str(value)
    try:
        d = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return d.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text

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
    cv2.imwrite(abs_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return f"screenshots/{filename}"  # luôn dùng "/" (os.path.join trên Windows sinh ra "\\" làm vỡ URL ảnh)


def frame_to_jpeg_bytes(frame) -> bytes:
    """Encode a frame as JPEG bytes for MJPEG streaming."""
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buffer.tobytes() if ok else b""