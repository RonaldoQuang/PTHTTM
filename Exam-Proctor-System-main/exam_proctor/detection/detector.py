"""
detection/detector.py
-----------------------
Quản lý tập trung các mô hình YOLO của dự án (Ensemble 5 models):
1. Pose Model (yolo11n-pose.pt): Xác định người và Keypoints tư thế.
2. Paper Model (train_myself-cheat_paper.pt): Nhận diện phao thi / tài liệu.
3. Object Model v1 (train_myself-phone_and_laptop.pt): Nhận diện thiết bị bản cũ.
4. Object Model v2 (train_myself-phone_and_laptop2.pt): Nhận diện thiết bị bản mới train trên Colab.
5. Phone Detection Model (phone_detection.pt): Nhận diện chuyên biệt điện thoại góc cuối lớp.
"""

import os
from typing import List, Dict, Any
from ultralytics import YOLO
from config.config import Config
from detection.detection_types import Detection

class PersonPhoneDetector:
    """Quản lý các mô hình AI và trả về kết quả nhận diện đã được cấu trúc."""

    def __init__(self, conf_threshold: float = None, device: str = None):
        self.conf_threshold = conf_threshold or getattr(Config, "YOLO_CONF_THRESHOLD", 0.5)
        self.device = device or getattr(Config, "DEVICE", "cpu")

        # Xác định thư mục chứa models
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        models_dir = os.path.join(project_root, "models")

        # Đường dẫn các file weights
        pose_path = os.path.join(models_dir, "yolo11n-pose.pt")
        paper_path = os.path.join(models_dir, "train_myself-cheat_paper.pt")
        object_v1_path = os.path.join(models_dir, "train_myself-phone_and_laptop.pt")
        object_v2_path = os.path.join(models_dir, "train_myself-phone_and_laptop2.pt")
        phone_custom_path = os.path.join(models_dir, "phone_detection.pt")

        print("[Detector] Loading All AI Models...")
        self.pose_model = YOLO(pose_path)
        self.paper_model = YOLO(paper_path)
        self.object_v1_model = YOLO(object_v1_path)
        self.object_v2_model = YOLO(object_v2_path)
        self.phone_custom_model = YOLO(phone_custom_path)

    def detect(self, frame) -> Dict[str, Any]:
        """
        Chạy inference trên tất cả các model và trả về Dict chứa kết quả phân loại
        """
        results = {
            "pose_results": None,
            "papers": [],
            "devices": []
        }

        try:
            # 1. Run Pose Detection (Tracking sinh viên & lấy Keypoints)
            pose_res = self.pose_model.track(
                source=frame,
                persist=True,
                conf=self.conf_threshold,
                tracker="bytetrack.yaml",
                device=self.device,
                verbose=False
            )
            results["pose_results"] = pose_res[0] if pose_res else None

            # 2. Run Detect Phao thi
            paper_res = self.paper_model.predict(
                source=frame,
                conf=0.4,
                device=self.device,
                verbose=False
            )
            if paper_res and len(paper_res[0].boxes) > 0:
                for box in paper_res[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    results["papers"].append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": conf,
                        "label": "cheat_paper"
                    })

            # 3. Run Detect Điện thoại & Laptop (Model V1 cũ)
            obj_v1_res = self.object_v1_model.predict(
                source=frame,
                conf=0.35,
                device=self.device,
                verbose=False
            )
            if obj_v1_res and len(obj_v1_res[0].boxes) > 0:
                names = obj_v1_res[0].names
                for box in obj_v1_res[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    results["devices"].append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": conf,
                        "label": names.get(cls_id, "device")
                    })

            # 4. Run Detect Điện thoại & Laptop (Model V2 mới train trên Colab)
            obj_v2_res = self.object_v2_model.predict(
                source=frame,
                conf=0.5,
                device=self.device,
                verbose=False
            )
            if obj_v2_res and len(obj_v2_res[0].boxes) > 0:
                names = obj_v2_res[0].names
                for box in obj_v2_res[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    results["devices"].append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": conf,
                        "label": names.get(cls_id, "device")
                    })

            # 5. Run Detect Điện thoại chuyên biệt góc cuối lớp (phone_detection.pt)
            phone_custom_res = self.phone_custom_model.predict(
                source=frame,
                conf=0.35,
                device=self.device,
                verbose=False
            )
            if phone_custom_res and len(phone_custom_res[0].boxes) > 0:
                for box in phone_custom_res[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    results["devices"].append({
                        "bbox": (x1, y1, x2, y2),
                        "confidence": conf,
                        "label": "phone"
                    })

        except Exception as e:
            print(f"[Detector Error] Inference fail: {e}")

        return results

    def split_persons_and_phones(self, detection_results: Dict[str, Any]):
        """
        Hàm tương thích ngược (Backward Compatibility) giúp các module cũ không bị crash.
        Tách kết quả thành (persons, devices/papers).
        """
        persons = []
        pose_res = detection_results.get("pose_results")

        if pose_res is not None and pose_res.boxes is not None:
            boxes = pose_res.boxes
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                track_id = int(box.id[0]) if box.id is not None else i
                
                det = Detection(
                    class_id=0,
                    label="person",
                    confidence=conf,
                    x1=x1, y1=y1, x2=x2, y2=y2
                )
                det.track_id = track_id
                persons.append(det)

        devices = detection_results.get("devices", [])
        papers = detection_results.get("papers", [])

        return persons, devices + papers