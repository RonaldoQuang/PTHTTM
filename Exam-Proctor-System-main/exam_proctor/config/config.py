# """
# config/config.py
# -----------------
# Central configuration for the AI Exam Proctoring System.
# All tunable parameters live here so the rest of the codebase never
# hard-codes thresholds, paths, or credentials.
# """

# import os
# from datetime import timedelta

# BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# class Config:
#     """Base configuration shared by all environments."""

#     # ---------------------------------------------------------------- Flask
#     SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
#     SESSION_TYPE = "filesystem"
#     PERMANENT_SESSION_LIFETIME = timedelta(hours=4)
#     SESSION_COOKIE_HTTPONLY = True
#     SESSION_COOKIE_SAMESITE = "Lax"

#     # ------------------------------------------------------------- Database
#     DB_PATH = os.path.join(BASE_DIR, "database", "proctor.db")
#     SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

#     # --------------------------------------------------------------- Paths
#     SCREENSHOT_DIR = os.path.join(BASE_DIR, "static", "screenshots")
#     REPORT_DIR = os.path.join(BASE_DIR, "static", "reports")
#     MODEL_DIR = os.path.join(BASE_DIR, "models")

#     # -------------------------------------------------------------- Camera
#     CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", 0)  # 0 = default webcam, or RTSP/HTTP URL
#     FRAME_WIDTH = 960
#     FRAME_HEIGHT = 540
#     STREAM_FPS_LIMIT = 15  # cap FPS to keep CPU inference usable

#     # ---------------------------------------------------------- AI Models
#     YOLO_MODEL_PATH = os.path.join(MODEL_DIR, "yolov8n.pt")  # person + phone base model
#     YOLO_CONF_THRESHOLD = 0.45
#     YOLO_PERSON_CLASS_ID = 0     # COCO class id for 'person'
#     YOLO_PHONE_CLASS_ID = 67     # COCO class id for 'cell phone'
#     DEVICE = os.environ.get("DEVICE", "cpu")  # 'cpu' or 'cuda:0'

#     # ------------------------------------------------------------ Tracking
#     TRACKER_TYPE = "bytetrack"       # 'bytetrack' or 'deepsort'
#     TRACK_MAX_AGE = 30               # frames a lost track is kept alive
#     TRACK_MATCH_IOU_THRESHOLD = 0.3

#     # ------------------------------------------------- Activity Analysis
#     HEAD_TURN_YAW_THRESHOLD = 25          # degrees, beyond which "looking away" fires
#     HEAD_TURN_SUSTAIN_FRAMES = 8          # consecutive frames required to count an event
#     FACE_MISSING_SECONDS_THRESHOLD = 6    # face not visible for N seconds -> event
#     STANDING_HEIGHT_RATIO_DELTA = 0.35    # bbox height growth ratio vs baseline -> standing
#     SEAT_LEAVE_ABSENCE_SECONDS = 10       # student's box gone from seat zone -> left seat
#     PROXIMITY_DISTANCE_PX = 80            # distance between two boxes considered "close"
#     PROXIMITY_SUSTAIN_SECONDS = 3
#     EVENT_COOLDOWN_SECONDS = 5            # min gap before the same event type re-fires per student

#     # --------------------------------------------------------- Scoring
#     SCORE_WEIGHTS = {
#         "looking_away": 2,
#         "mobile_phone": 10,
#         "standing": 5,
#         "left_seat": 8,
#         "object_passing": 7,
#         "face_not_visible": 4,
#         "close_interaction": 3,
#     }
#     SUSPICION_ALERT_THRESHOLD = 15   # score at which a student is flagged/highlighted
#     SCORE_DECAY_PER_MINUTE = 1       # slow decay so old minor events don't haunt forever

#     # ------------------------------------------------------------- Reports
#     REPORT_LOGO_TEXT = "AI Exam Proctoring System"

#     @staticmethod
#     def ensure_directories():
#         for path in [
#             Config.SCREENSHOT_DIR,
#             Config.REPORT_DIR,
#             Config.MODEL_DIR,
#             os.path.dirname(Config.DB_PATH),
#         ]:
#             os.makedirs(path, exist_ok=True)


# class DevelopmentConfig(Config):
#     DEBUG = True


# class ProductionConfig(Config):
#     DEBUG = False


# CONFIG_MAP = {
#     "development": DevelopmentConfig,
#     "production": ProductionConfig,
# }


"""
config/config.py
-----------------
Central configuration for the AI Exam Proctoring System.
All tunable parameters live here so the rest of the codebase never
hard-codes thresholds, paths, or credentials.
"""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    """Base configuration shared by all environments."""

    # ---------------------------------------------------------------- Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ------------------------------------------------------------- Database
    DB_PATH = os.path.join(BASE_DIR, "database", "proctor.db")
    SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

    # --------------------------------------------------------------- Paths
    SCREENSHOT_DIR = os.path.join(BASE_DIR, "static", "screenshots")
    REPORT_DIR = os.path.join(BASE_DIR, "static", "reports")
    MODEL_DIR = os.path.join(BASE_DIR, "models")

    # -------------------------------------------------------------- Camera
    CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", 0)  # 0 = default webcam, or RTSP/HTTP URL
    FRAME_WIDTH = 960
    FRAME_HEIGHT = 540
    STREAM_FPS_LIMIT = 15  # cap FPS to keep CPU inference usable

    # ---------------------------------------------------------- AI Models (Custom Team Models)
    MODEL_POSE_PATH = os.path.join(MODEL_DIR, "yolo11n-pose.pt")
    MODEL_PAPER_PATH = os.path.join(MODEL_DIR, "train_myself-cheat_paper.pt")
    MODEL_OBJECT_PATH = os.path.join(MODEL_DIR, "train_myself-phone_and_laptop.pt")

    # Ngưỡng nhận diện riêng cho từng model để loại bỏ Bounding Box ảo
    POSE_CONF_THRESHOLD = 0.50
    PAPER_CONF_THRESHOLD = 0.40
    OBJECT_CONF_THRESHOLD = 0.40
    
    YOLO_CONF_THRESHOLD = 0.45  # Tương thích ngược
    DEVICE = os.environ.get("DEVICE", "cpu")  # 'cpu' or 'cuda:0'

    # ------------------------------------------------------------ Tracking
    TRACKER_TYPE = "bytetrack"       # 'bytetrack' or 'deepsort'
    TRACK_MAX_AGE = 30               # frames a lost track is kept alive
    TRACK_MATCH_IOU_THRESHOLD = 0.3

    # ------------------------------------------------- Activity Analysis
    HEAD_TURN_YAW_THRESHOLD = 25          # degrees, beyond which "looking away" fires
    HEAD_TURN_SUSTAIN_FRAMES = 8          # consecutive frames required to count an event
    FACE_MISSING_SECONDS_THRESHOLD = 6    # face not visible for N seconds -> event
    STANDING_HEIGHT_RATIO_DELTA = 0.35    # bbox height growth ratio vs baseline -> standing
    SEAT_LEAVE_ABSENCE_SECONDS = 10       # student's box gone from seat zone -> left seat
    PROXIMITY_DISTANCE_PX = 80            # distance between two boxes considered "close"
    PROXIMITY_SUSTAIN_SECONDS = 3
    EVENT_COOLDOWN_SECONDS = 5            # min gap before the same event type re-fires per student

    # --------------------------------------------------------- Scoring
    SCORE_WEIGHTS = {
        "looking_away": 2,
        "mobile_phone": 10,
        "cheat_paper": 10,    # Thêm trọng số điểm cho vi phạm sử dụng phao thi
        "laptop": 8,          # Thêm trọng số điểm cho laptop/thiết bị điện tử
        "standing": 5,
        "left_seat": 8,
        "object_passing": 7,
        "face_not_visible": 4,
        "close_interaction": 3,
    }
    SUSPICION_ALERT_THRESHOLD = 15   # score at which a student is flagged/highlighted
    SCORE_DECAY_PER_MINUTE = 1       # slow decay so old minor events don't haunt forever

    # ------------------------------------------------------------- Reports
    REPORT_LOGO_TEXT = "AI Exam Proctoring System"

    @staticmethod
    def ensure_directories():
        for path in [
            Config.SCREENSHOT_DIR,
            Config.REPORT_DIR,
            Config.MODEL_DIR,
            os.path.dirname(Config.DB_PATH),
        ]:
            os.makedirs(path, exist_ok=True)


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}