"""
core/monitoring_service.py
--------------------------
Luồng xử lý chính kết hợp hệ thống Ensemble nhiều mô hình AI:
1. YOLOv11 Pose (Tracking & Phân tích góc Quay đầu, Cúi đầu, Giơ tay)
2. Custom YOLO Phao thi (cheat_paper)
3. Custom YOLO Thiết bị v1 & v2 (phone_and_laptop)
4. Custom YOLO Chuyên biệt điện thoại góc cuối lớp (phone_detection)
"""

import threading
import time
import cv2
import numpy as np
import math
from ultralytics import YOLO
import sys
from pathlib import Path

# Đảm bảo thư mục exam_proctor luôn nằm trong sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from camera.camera_manager import CameraManager


# --- Hàm tính góc giữa 3 điểm A-B-C (B là đỉnh góc) ---
def calculate_angle(A, B, C):
    if A[2] < 0.2 or B[2] < 0.2 or C[2] < 0.2:
        return None  # Không đủ độ tin cậy điểm
    
    ba = np.array([A[0] - B[0], A[1] - B[1]])
    bc = np.array([C[0] - B[0], C[1] - B[1]])
    
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    
    if norm_ba == 0 or norm_bc == 0:
        return None
        
    cosine_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    angle = np.arccos(cosine_angle)
    return np.degrees(angle)


class MonitoringService:
    def __init__(self, db_manager=None, exam_id=1, camera_manager=None, camera_source=None, **kwargs):
        self.db = db_manager
        self.exam_id = exam_id
        
        # 1. Xử lý khởi tạo CameraManager an toàn
        if camera_manager is not None:
            self.camera_manager = camera_manager
        else:
            src = camera_source if (camera_source is not None and camera_source != '') else 0
            if isinstance(src, str) and src.isdigit():
                src = int(src)
            self.camera_manager = CameraManager(source=src)

        if camera_source is not None and camera_source != '':
            src = camera_source
            if isinstance(src, str) and src.isdigit():
                src = int(src)
            self.camera_manager.source = src

        # --- 2. Load tất cả các Model AI (Ensemble) ---
        print("[MonitoringService] Loading all AI models...")
        self.pose_model = YOLO("models/yolo11n-pose.pt")
        self.paper_model = YOLO("models/train_myself-cheat_paper.pt")
        self.object_v1_model = YOLO("models/train_myself-phone_and_laptop.pt")
        self.object_v2_model = YOLO("models/train_myself-phone_and_laptop2.pt")
        self.phone_custom_model = YOLO("models/phone_detection.pt")

        self.is_running = False
        self.thread = None
        self.latest_frame = None
        self.lock = threading.Lock()

        self.student_scores = {}

    def start(self, source=None) -> bool:
        if self.is_running:
            return True

        if source is not None and source != '':
            src = source
            if isinstance(src, str) and src.isdigit():
                src = int(src)
            self.camera_manager.source = src

        if not self.camera_manager.open():
            return False

        self.is_running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.camera_manager:
            self.camera_manager.release()

    def _analyze_pose_warnings(self, person_kpts, box=None):
        nose = person_kpts[0]
        l_eye, r_eye = person_kpts[1], person_kpts[2]
        l_ear, r_ear = person_kpts[3], person_kpts[4]
        l_shoulder, r_shoulder = person_kpts[5], person_kpts[6]
        l_hip, r_hip = person_kpts[11], person_kpts[12]
        l_wrist, r_wrist = person_kpts[9], person_kpts[10]

        warnings = []

        shoulder_width = 0
        if l_shoulder[2] > 0.3 and r_shoulder[2] > 0.3:
            shoulder_width = abs(l_shoulder[0] - r_shoulder[0])

        mid_shoulder = [
            (l_shoulder[0] + r_shoulder[0]) / 2.0, 
            (l_shoulder[1] + r_shoulder[1]) / 2.0, 
            min(l_shoulder[2], r_shoulder[2])
        ]
        mid_hip = [
            (l_hip[0] + r_hip[0]) / 2.0, 
            (l_hip[1] + r_hip[1]) / 2.0, 
            min(l_hip[2], r_hip[2])
        ]

        # QUAY ĐẦU
        is_turning_head = False
        if nose[2] > 0.3 and l_eye[2] > 0.3 and r_eye[2] > 0.3:
            dist_l = abs(nose[0] - l_eye[0])
            dist_r = abs(nose[0] - r_eye[0])
            if dist_r > 0 and (dist_l / dist_r > 2.5 or dist_r / dist_l > 2.5):
                is_turning_head = True
        elif (l_eye[2] > 0.3 and r_eye[2] < 0.15) or (r_eye[2] > 0.3 and l_eye[2] < 0.15):
            is_turning_head = True
        elif (l_ear[2] > 0.3 and r_ear[2] < 0.1) or (r_ear[2] > 0.3 and l_ear[2] < 0.1):
            is_turning_head = True

        if is_turning_head:
            warnings.append("QUAY DAU")

        # CÚI GẦM MẶT & CÚI ĐẦU THẤP
        face_lost = (nose[2] < 0.15 and l_eye[2] < 0.15 and r_eye[2] < 0.15)
        shoulders_visible = (l_shoulder[2] > 0.3 or r_shoulder[2] > 0.3)
        if face_lost and shoulders_visible:
            warnings.append("CUI GAM MAT")

        angle_head_body = calculate_angle(nose, mid_shoulder, mid_hip)
        if angle_head_body is not None and angle_head_body < 115:
            warnings.append("CUI DAU THAP")

        # GIƠ TAY CAO
        if (l_wrist[2] > 0.3 and l_eye[2] > 0.3 and l_wrist[1] < l_eye[1]) or \
           (r_wrist[2] > 0.3 and r_eye[2] > 0.3 and r_wrist[1] < r_eye[1]):
            warnings.append("GIO TAY CAO")

        # NẰM RA BÀN
        if shoulders_visible and mid_shoulder[2] > 0.3 and mid_hip[2] > 0.3 and shoulder_width > 5:
            vertical_torso_dist = abs(mid_shoulder[1] - mid_hip[1])
            if vertical_torso_dist < (0.55 * shoulder_width) and face_lost:
                warnings.append("NAM RA BAN")

        # ĐỨNG DẬY
        if box is not None:
            box_height = box[3] - box[1]
            box_width = box[2] - box[0]
            if box_width > 0:
                aspect_ratio = box_height / box_width
                if aspect_ratio > 1.65 and box_height > 100:
                    warnings.append("DUNG DAY")

        return warnings

    def _process_loop(self):
        print("[MonitoringService] Loop started processing frames with ensemble models...")
        while self.is_running:
            success, frame = self.camera_manager.read()
            if not success or frame is None:
                time.sleep(0.01)
                continue

            annotated_frame = frame.copy()

            try:
                # --- Predict từ các Model ---
                pose_results = self.pose_model.track(
                    frame, persist=True, conf=0.4, tracker="bytetrack.yaml", verbose=False
                )

                paper_results = self.paper_model(frame, conf=0.5, verbose=False)
                
                # Dùng ngưỡng conf=0.5 để lọc bỏ các trường hợp nhận diện nhầm (như khung cửa sổ)
                obj_v1_results = self.object_v1_model(frame, conf=0.5, verbose=False)
                obj_v2_results = self.object_v2_model(frame, conf=0.5, verbose=False)
                phone_custom_results = self.phone_custom_model(frame, conf=0.4, verbose=False)

                # --- 1. Vẽ Phao Thi ---
                for res in paper_results:
                    for box in res.boxes:
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.putText(annotated_frame, f"cheat_paper {conf:.2f}", (x1, max(15, y1 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2, cv2.LINE_AA)

                # --- 2. Hàm phụ trợ vẽ thiết bị (Phân biệt màu Laptop và Phone) ---
                def draw_devices(results_list, default_label="device"):
                    for res in results_list:
                        names = res.names
                        for box in res.boxes:
                            cls_id = int(box.cls[0])
                            label = names.get(cls_id, default_label)
                            conf = float(box.conf[0])
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            
                            # Lọc bỏ các box quá dài/quá dẹt (như khung cửa sổ dọc)
                            w = x2 - x1
                            h = y2 - y1
                            if w > 0 and h > 0:
                                ratio = h / w
                                if ratio > 4.0 and "laptop" in label.lower():
                                    continue

                            # Phân định màu sắc dựa theo nhãn (label)
                            if "phone" in label.lower():
                                box_color = (255, 255, 255)  # Trắng cho điện thoại
                                text_color = (255, 255, 255)
                            else:
                                box_color = (0, 165, 255)    # Cam cho laptop/thiết bị khác
                                text_color = (0, 165, 255)

                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), box_color, 2)
                            cv2.putText(annotated_frame, f"{label} {conf:.2f}", (x1, max(15, y1 - 8)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2, cv2.LINE_AA)

                draw_devices(obj_v1_results, "device")
                draw_devices(obj_v2_results, "device")
                draw_devices(phone_custom_results, "phone")

                # --- 3. Process Sinh Viên (Pose & Phân tích hành vi ưu tiên sạch sẽ) ---
                if pose_results and len(pose_results[0].keypoints) > 0:
                    boxes = pose_results[0].boxes.xyxy.cpu().numpy()
                    keypoints_list = pose_results[0].keypoints.data.cpu().numpy()

                    for box, kpts in zip(boxes, keypoints_list):
                        x1, y1, x2, y2 = map(int, box[:4])
                        
                        warnings = self._analyze_pose_warnings(kpts, box)
                        
                        if len(warnings) > 0:
                            # Sắp xếp và ưu tiên lấy hành vi quan trọng nhất
                            priority_order = ["DUNG DAY", "NAM RA BAN", "GIO TAY CAO", "QUAY DAU", "CUI GAM MAT", "CUI DAU THAP"]
                            
                            selected_warning = None
                            for p in priority_order:
                                matched = [w for w in warnings if p in w]
                                if matched:
                                    selected_warning = matched[0]
                                    break
                            
                            if not selected_warning and warnings:
                                selected_warning = warnings[0]

                            # Vẽ khung đỏ và hiển thị đúng 1 cảnh báo trọng tâm nhất cho mỗi sinh viên
                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                            warning_text = f"CANH BAO: {selected_warning}"
                            cv2.putText(
                                annotated_frame, 
                                warning_text, 
                                (x1, max(20, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 
                                0.55, 
                                (0, 0, 255), 
                                2, 
                                cv2.LINE_AA
                            )

            except Exception as e:
                print(f"[MonitoringService] Inference Error: {e}")

            with self.lock:
                self.latest_frame = annotated_frame

            time.sleep(0.01)

    def get_latest_frame(self):
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None