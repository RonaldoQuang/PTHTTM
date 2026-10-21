# """
# analysis/head_pose.py
# -----------------------
# Uses MediaPipe FaceMesh to estimate head yaw/pitch (via solvePnP on a
# handful of stable facial landmarks) for a cropped student region, and
# to report whether a face was found at all (used for the
# "face not visible" indicator, e.g. looking straight down at a phone
# or turning fully away).
# """

# import cv2
# import numpy as np

# try:
#     import mediapipe as mp
# except Exception as exc:  # pragma: no cover - environment-dependent fallback
#     mp = None
#     _MEDIAPIPE_IMPORT_ERROR = exc
# else:
#     _MEDIAPIPE_IMPORT_ERROR = None

# # Stable landmark indices used for the 6-point head-pose model
# # (nose tip, chin, left eye corner, right eye corner, left mouth, right mouth)
# _LANDMARK_IDS = [1, 152, 33, 263, 61, 291]

# # Generic 3D model points (mm) corresponding to _LANDMARK_IDS, used for solvePnP
# _MODEL_POINTS_3D = np.array([
#     (0.0, 0.0, 0.0),          # nose tip
#     (0.0, -63.6, -12.5),      # chin
#     (-43.3, 32.7, -26.0),     # left eye corner
#     (43.3, 32.7, -26.0),      # right eye corner
#     (-28.9, -28.9, -24.1),    # left mouth corner
#     (28.9, -28.9, -24.1),     # right mouth corner
# ], dtype=np.float64)


# class HeadPoseEstimator:
#     """Wraps a MediaPipe FaceMesh instance for per-crop head pose estimation."""

#     def __init__(self, max_faces: int = 1):
#         self._face_mesh = None
#         self._import_error = _MEDIAPIPE_IMPORT_ERROR

#         if mp is None:
#             return

#         try:
#             self._mp_face_mesh = mp.solutions.face_mesh
#             self._face_mesh = self._mp_face_mesh.FaceMesh(
#                 static_image_mode=True,
#                 max_num_faces=max_faces,
#                 refine_landmarks=False,
#                 min_detection_confidence=0.5,
#             )
#         except Exception as exc:  # pragma: no cover - environment-dependent fallback
#             self._import_error = exc
#             self._face_mesh = None

#     def estimate(self, student_crop):
#         """
#         Returns a dict: {"face_found": bool, "yaw": float, "pitch": float}
#         yaw/pitch are in degrees; positive yaw = turned to their right.
#         Returns face_found=False if no face landmarks could be located
#         (e.g. head turned fully away, occluded, or looking down).
#         """
#         if student_crop is None or student_crop.size == 0 or self._face_mesh is None:
#             return {"face_found": False, "yaw": 0.0, "pitch": 0.0}

#         h, w = student_crop.shape[:2]
#         rgb = cv2.cvtColor(student_crop, cv2.COLOR_BGR2RGB)
#         results = self._face_mesh.process(rgb)

#         if not results.multi_face_landmarks:
#             return {"face_found": False, "yaw": 0.0, "pitch": 0.0}

#         landmarks = results.multi_face_landmarks[0].landmark
#         try:
#             image_points = np.array(
#                 [(landmarks[i].x * w, landmarks[i].y * h) for i in _LANDMARK_IDS],
#                 dtype=np.float64,
#             )
#         except IndexError:
#             return {"face_found": False, "yaw": 0.0, "pitch": 0.0}

#         focal_length = w
#         center = (w / 2, h / 2)
#         camera_matrix = np.array([
#             [focal_length, 0, center[0]],
#             [0, focal_length, center[1]],
#             [0, 0, 1],
#         ], dtype=np.float64)
#         dist_coeffs = np.zeros((4, 1))

#         success, rotation_vec, _ = cv2.solvePnP(
#             _MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
#             flags=cv2.SOLVEPNP_ITERATIVE,
#         )
#         if not success:
#             return {"face_found": True, "yaw": 0.0, "pitch": 0.0}

#         rotation_matrix, _ = cv2.Rodrigues(rotation_vec)
#         sy = np.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
#         pitch = np.degrees(np.arctan2(-rotation_matrix[2, 0], sy))
#         yaw = np.degrees(np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))

#         return {"face_found": True, "yaw": float(yaw), "pitch": float(pitch)}

#     def close(self):
#         if self._face_mesh is not None:
#             self._face_mesh.close()


"""
analysis/head_pose.py
-----------------------
Uses MediaPipe FaceMesh to estimate head yaw/pitch (via solvePnP on a
handful of stable facial landmarks) for a cropped student region.
"""

import cv2
import numpy as np

try:
    import mediapipe as mp
except Exception as exc:
    mp = None
    _MEDIAPIPE_IMPORT_ERROR = exc
else:
    _MEDIAPIPE_IMPORT_ERROR = None

_LANDMARK_IDS = [1, 152, 33, 263, 61, 291]

_MODEL_POINTS_3D = np.array([
    (0.0, 0.0, 0.0),          # nose tip
    (0.0, -63.6, -12.5),      # chin
    (-43.3, 32.7, -26.0),     # left eye corner
    (43.3, 32.7, -26.0),      # right eye corner
    (-28.9, -28.9, -24.1),    # left mouth corner
    (28.9, -28.9, -24.1),     # right mouth corner
], dtype=np.float64)


class HeadPoseEstimator:
    """Wraps a MediaPipe FaceMesh instance for per-crop head pose estimation."""

    def __init__(self, max_faces: int = 1):
        self._face_mesh = None
        self._import_error = _MEDIAPIPE_IMPORT_ERROR

        if mp is None:
            return

        try:
            self._mp_face_mesh = mp.solutions.face_mesh
            self._face_mesh = self._mp_face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=max_faces,
                refine_landmarks=False,
                min_detection_confidence=0.5,
            )
        except Exception as exc:
            self._import_error = exc
            self._face_mesh = None

    def estimate(self, student_crop):
        if student_crop is None or student_crop.size == 0 or self._face_mesh is None:
            return {"face_found": True, "yaw": 0.0, "pitch": 0.0}

        h, w = student_crop.shape[:2]
        try:
            rgb = cv2.cvtColor(student_crop, cv2.COLOR_BGR2RGB)
            results = self._face_mesh.process(rgb)

            if not results or not results.multi_face_landmarks:
                return {"face_found": True, "yaw": 0.0, "pitch": 0.0}

            landmarks = results.multi_face_landmarks[0].landmark
            image_points = np.array(
                [(landmarks[i].x * w, landmarks[i].y * h) for i in _LANDMARK_IDS],
                dtype=np.float64,
            )
        except Exception:
            return {"face_found": True, "yaw": 0.0, "pitch": 0.0}

        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1))

        success, rotation_vec, _ = cv2.solvePnP(
            _MODEL_POINTS_3D, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return {"face_found": True, "yaw": 0.0, "pitch": 0.0}

        rotation_matrix, _ = cv2.Rodrigues(rotation_vec)
        sy = np.sqrt(rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2)
        pitch = np.degrees(np.arctan2(-rotation_matrix[2, 0], sy))
        yaw = np.degrees(np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))

        return {"face_found": True, "yaw": float(yaw), "pitch": float(pitch)}

    def close(self):
        if self._face_mesh is not None:
            self._face_mesh.close()