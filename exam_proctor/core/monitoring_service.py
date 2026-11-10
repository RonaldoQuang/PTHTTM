"""
core/monitoring_service.py
--------------------------
Điều phối luồng xử lý chính (chỉ "nhạc trưởng": đọc camera -> chạy model -> gọi các module -> vẽ lên video).
Ensemble 4 model:
  1. YOLO11-pose           : tìm người + keypoint + ByteTrack gán ID
  2. cheat_paper           : phao thi
  3. phone_and_laptop2     : điện thoại + laptop
  4. phone_detection       : điện thoại (chỉ lấy lớp "phone")

Các việc khác nằm ở module riêng:
  detection/model_loader.py   nạp model (OpenVINO / .pt)
  analysis/pose_rules.py      luật hành vi từ keypoint
  tracking/seat_mapper.py     ID tracker -> số chỗ ngồi
  analysis/event_filters.py   lọc hành vi kéo dài + gán vật thể cho thí sinh
  analysis/scoring.py         điểm nghi ngờ
  core/incident_recorder.py   lưu sự cố, ảnh bằng chứng
"""
import math
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

# Đảm bảo thư mục exam_proctor luôn nằm trong sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analysis.event_filters import SustainFilter, assign_objects
from analysis.pose_rules import analyze_pose_warnings, pick_main_warning
from camera.camera_manager import CameraManager
from config.config import Config
from core.incident_recorder import IncidentRecorder
from detection.model_loader import MODEL_DIR, check_required_models, load_yolo
from tracking.seat_mapper import SeatMapper
from utils.helpers import incident_label, draw_texts_vi

TRACKER_CONFIG = BASE_DIR / "config" / "bytetrack_exam.yaml"


class MonitoringService:
    def __init__(self, db_manager=None, exam_id=1, camera_manager=None, camera_source=None,
                 recorder=None, **kwargs):
        self.db = db_manager
        self.exam_id = exam_id

        # --- Camera ---
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

        # --- Model AI ---
        print("[MonitoringService] Loading all AI models...")
        self.pose_model = load_yolo("yolo11n-pose.pt", "pose", imgsz=Config.POSE_IMGSZ)
        # Model vật thể: ưu tiên 1 model gộp 3 lớp (phone/laptop/cheat_paper) đã fine-tune trên dữ liệu của bạn;
        # không có thì dùng 3 model rời cũ. Mỗi mục: (model, ngưỡng conf, lọc lớp)
        merged_path = MODEL_DIR / Config.OBJECT_MODEL_FILE
        if merged_path.exists() or (MODEL_DIR / (merged_path.stem + "_openvino_model")).exists():
            print(f"[MonitoringService] Dùng model vật thể gộp: {Config.OBJECT_MODEL_FILE}")
            self.obj_models = [(load_yolo(Config.OBJECT_MODEL_FILE, "detect", imgsz=Config.OBJECT_IMGSZ), Config.OBJECT_MODEL_CONF, None)]
            self.OBJ_STRIDE = getattr(Config, "OBJECT_SCAN_STRIDE", 6)
        else:
            check_required_models()
            self.obj_models = [
                (load_yolo("train_myself-cheat_paper.pt", "detect", imgsz=Config.OBJECT_IMGSZ), 0.45, None),
                (load_yolo("train_myself-phone_and_laptop2.pt", "detect", imgsz=Config.OBJECT_IMGSZ), 0.45, None),
            ]
            if Config.USE_INCAR_PHONE_MODEL:
                # phone_detection.pt có 6 lớp (drinking, drowsy, phone, seatbelt, smoking, yawning) -> chỉ lấy "phone"
                phone_model = load_yolo("phone_detection.pt", "detect", imgsz=Config.OBJECT_IMGSZ)
                phone_ids = [k for k, v in phone_model.names.items() if v == "phone"]
                self.obj_models.append((phone_model, 0.35, phone_ids))
            # luân phiên: mỗi OBJ_STRIDE frame chạy 1 model (cách N frame chạy 1 lần giúp giảm tải CPU)
            self.OBJ_STRIDE = getattr(Config, "OBJECT_SCAN_STRIDE", 6)

        # --- Các module phân tích ---
        self.seats = SeatMapper()
        self.sustain = SustainFilter(pose_sustain=2.0, object_sustain=1.0)
        self.recorder = recorder or IncidentRecorder(db_manager, exam_id)

        # --- Trạng thái chạy ---
        self.is_running = False
        self.thread = None
        self.latest_frame = None
        self.lock = threading.Lock()
        self.active_tracks = 0

        # --- Cấu hình tốc độ / độ nhạy ---
        self.PROCESS_WIDTH = Config.POSE_IMGSZ     # độ phân giải model pose (xem config.py)
        self.OBJ_WIDTH = Config.OBJECT_IMGSZ       # độ phân giải model vật thể
        self.POSE_CONF = 0.25        # ngưỡng phân tích hành vi (bắt cả người ở xa)
        self.POSE_CONF_LOW = 0.12    # ngưỡng thấp để ByteTrack giữ ID khi người bị che / mờ
        self.frame_count = 0
        self.obj_cache = None
        self.overlay_mask = None     # vị trí các nét vẽ cảnh báo, phủ lên video mượt
        self.fps = 0.0
        self._fps_t = time.time()
        self._fps_n = 0

        # Luồng đọc cam riêng: luôn giữ frame mới nhất, bỏ frame cũ
        self.reader_thread = None
        self.use_reader = False
        self._raw_frame = None
        self._raw_id = 0
        self._last_id = 0
        self._raw_lock = threading.Lock()

        # File video: phát đúng tốc độ thật, tự bỏ qua frame khi AI xử lý không kịp (False = xử lý từng frame)
        self.REALTIME_FILE = True
        self._play_t0 = None
        self._play_fps = 25.0

        self.tracker_cfg = str(TRACKER_CONFIG) if TRACKER_CONFIG.exists() else "bytetrack.yaml"
        self._warmup()

    def _clock(self):
        """Đồng hồ dùng cho lọc hành vi/cooldown (evaluate.py ghi đè để dùng thời gian của video)."""
        return time.time()

    # ------------------------------------------------------------------ vòng đời
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

        # Xóa dữ liệu của phiên trước
        self.seats.reset()
        self.sustain.reset()
        self.recorder.reset()
        self.latest_frame = None
        self.overlay_mask = None
        self.obj_cache = None
        self._raw_frame = None
        self._raw_id = 0
        self._last_id = 0
        self._play_t0 = None
        self.frame_count = 0

        self.is_running = True
        self.use_reader = self._is_live_source(self.camera_manager.source)
        if self.use_reader:
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=2.0)
        if self.camera_manager:
            self.camera_manager.release()

    def _warmup(self):
        """Chạy thử 1 frame trống: lần bấm "Bắt đầu" đầu tiên không bị khựng và kiểm tra luôn cấu hình tracker."""
        blank = np.zeros((450, self.PROCESS_WIDTH, 3), dtype=np.uint8)
        blank_obj = np.zeros((360, self.OBJ_WIDTH, 3), dtype=np.uint8)
        try:
            self.pose_model.track(blank, persist=True, conf=self.POSE_CONF_LOW, imgsz=self.PROCESS_WIDTH,
                                  tracker=self.tracker_cfg, verbose=False)
        except Exception as exc:
            print(f"[MonitoringService] Không dùng được cấu hình tracker tùy chỉnh ({exc}), dùng bytetrack.yaml mặc định")
            self.tracker_cfg = "bytetrack.yaml"
            try:
                self.pose_model.track(blank, persist=True, conf=self.POSE_CONF_LOW, imgsz=self.PROCESS_WIDTH,
                                      tracker=self.tracker_cfg, verbose=False)
            except Exception as exc2:
                print(f"[MonitoringService] Warmup pose lỗi: {exc2}")
        for model, _, _ in self.obj_models:
            try:
                model(blank_obj, imgsz=self.OBJ_WIDTH, verbose=False)
            except Exception:
                pass

    # ------------------------------------------------------------------ đọc camera
    @staticmethod
    def _is_live_source(src):
        """Webcam / cam điện thoại (URL) -> True. File video -> False."""
        s = str(src).strip().lower()
        return s.isdigit() or s.startswith(("http://", "https://", "rtsp://"))

    def _reader_loop(self):
        """Đọc cam liên tục để buffer không bị đầy frame cũ."""
        while self.is_running:
            ok, frame = self.camera_manager.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            with self._raw_lock:
                self._raw_frame = frame
                self._raw_id += 1

    def _next_frame(self):
        """Lấy frame mới nhất. Trả về (False, None) nếu chưa có frame mới."""
        if not self.use_reader:
            return self._next_file_frame()
        with self._raw_lock:
            if self._raw_frame is None or self._raw_id == self._last_id:
                return False, None
            self._last_id = self._raw_id
            return True, self._raw_frame

    def _next_file_frame(self):
        """File video: bỏ qua các frame đã "quá giờ" để video phát đúng tốc độ thật (AI chậm hơn video)."""
        cap = self.camera_manager.cap
        if cap is None or not self.REALTIME_FILE:
            return self.camera_manager.read()
        now = time.time()
        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        if self._play_t0 is None:
            fps = cap.get(cv2.CAP_PROP_FPS)
            self._play_fps = fps if 1 < fps < 120 else 25.0
            self._play_t0 = now - pos / self._play_fps
        lag = int((now - self._play_t0) * self._play_fps - pos)
        if lag > 300:                       # tạm dừng quá lâu: đồng hồ lại từ vị trí hiện tại, không tua cả đoạn
            self._play_t0 = now - pos / self._play_fps
            lag = 0
        for _ in range(max(0, lag)):
            if not cap.grab():
                break
        ok, frame = self.camera_manager.read()
        if cap.get(cv2.CAP_PROP_POS_FRAMES) < pos:    # hết video, CameraManager quay lại từ đầu
            self._play_t0 = now
        return ok, frame

    def get_live_stats(self):
        """Dashboard dùng để hiển thị số sinh viên đang được theo dõi."""
        return {"active": self.is_running, "active_tracks": self.active_tracks, "fps": round(self.fps, 1)}

    def _resize(self, frame):
        h, w = frame.shape[:2]
        if w > self.PROCESS_WIDTH:
            frame = cv2.resize(frame, (self.PROCESS_WIDTH, int(h * self.PROCESS_WIDTH / w)))
        return frame

    # ------------------------------------------------------------------ xử lý 1 frame
    def _run_object_models(self, frame):
        """Chạy model vật thể. Nhiều model thì chạy luân phiên (mỗi OBJ_STRIDE frame chạy 1 model, còn lại dùng kết quả cũ)."""
        obj_h = int(frame.shape[0] * self.OBJ_WIDTH / frame.shape[1])
        if self.obj_cache is None:
            frame_obj = cv2.resize(frame, (self.OBJ_WIDTH, obj_h))
            self.obj_cache = [m(frame_obj, conf=c, classes=cl, imgsz=self.OBJ_WIDTH, verbose=False)
                              for m, c, cl in self.obj_models]
        elif self.frame_count % self.OBJ_STRIDE == 0:
            i = (self.frame_count // self.OBJ_STRIDE) % len(self.obj_models)
            m, c, cl = self.obj_models[i]
            frame_obj = cv2.resize(frame, (self.OBJ_WIDTH, obj_h))
            self.obj_cache[i] = m(frame_obj, conf=c, classes=cl, imgsz=self.OBJ_WIDTH, verbose=False)
        self.frame_count += 1

    @staticmethod
    def _object_kind(class_name):
        """Tên lớp của model -> loại sự cố. Nhận cả model cũ lẫn model gộp mới."""
        n = class_name.lower()
        if "phone" in n:
            return "mobile_phone"
        if "laptop" in n:
            return "laptop"
        if "paper" in n or "cheat" in n or "document" in n:
            return "cheat_paper"
        return None

    def _draw_objects(self, annotated, frame, texts):
        """Vẽ phao thi/điện thoại/laptop lên video, trả về danh sách vật thể [(loại, conf, bbox)]."""
        obj_scale = frame.shape[1] / self.OBJ_WIDTH
        obj_dets = []
        styles = {"cheat_paper": ("Phao thi", (255, 0, 0)),          # xanh dương
                  "mobile_phone": ("Điện thoại", (255, 255, 255)),   # trắng
                  "laptop": ("Laptop", (0, 165, 255))}               # cam
        for results in self.obj_cache:
            for res in results:
                for box in res.boxes:
                    kind = self._object_kind(res.names.get(int(box.cls[0]), ""))
                    if kind is None or kind not in Config.OBJECT_KINDS_ENABLED:
                        continue
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = [int(v * obj_scale) for v in box.xyxy[0]]
                    w, h = x2 - x1, y2 - y1
                    # Lọc bỏ các box laptop quá dài/dẹt (như khung cửa sổ dọc)
                    if kind == "laptop" and w > 0 and h > 0 and h / w > 4.0:
                        continue
                    label, color = styles[kind]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    texts.append((f"{label} {conf:.2f}", (x1, max(15, y1 - 8)), color, 16))
                    obj_dets.append((kind, conf, (x1, y1, x2, y2)))
        return obj_dets

    def _process_persons(self, pose_results, annotated, texts):
        """Phân tích từng thí sinh. Trả về (persons [(chỗ, bbox)], events [(chỗ, hành vi, conf, bbox)])."""
        persons, events = [], []
        self.seats.begin_frame()
        if not (pose_results and len(pose_results[0].keypoints) > 0):
            return persons, events

        boxes = pose_results[0].boxes.xyxy.cpu().numpy()
        keypoints_list = pose_results[0].keypoints.data.cpu().numpy()
        ids = pose_results[0].boxes.id
        ids = ids.int().cpu().tolist() if ids is not None else [None] * len(boxes)
        confs = pose_results[0].boxes.conf.cpu().tolist()
        self.active_tracks = sum(1 for c in confs if c >= self.POSE_CONF)

        for box, kpts, tid, conf in zip(boxes, keypoints_list, ids, confs):
            if conf < self.POSE_CONF:
                continue   # chỉ để tracker giữ ID, không phân tích hành vi
            x1, y1, x2, y2 = map(int, box[:4])
            seat = self.seats.assign(tid, (x1, y1, x2, y2))   # ID tracker -> số chỗ ngồi
            if seat is not None:
                hands = [(float(k[0]), float(k[1])) for k in (kpts[9], kpts[10]) if k[2] > 0.3]   # cổ tay thấy rõ
                persons.append((seat, (x1, y1, x2, y2), hands))

            main_warning = pick_main_warning(analyze_pose_warnings(kpts, box))
            if main_warning:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                texts.append((f"CẢNH BÁO: {incident_label(main_warning)}", (x1, max(20, y1 - 10)), (0, 0, 255), 18))
                events.append((seat, main_warning, conf, (x1, y1, x2, y2)))
            else:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 0), 1)
                label_str = f"Cho #{seat}" if seat is not None else "TS"
                cv2.putText(annotated, label_str, (x1, max(14, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 0), 1, cv2.LINE_AA)
        return persons, events

    def _process_frame(self, raw_frame):
        """Xử lý 1 frame: chạy model, phân tích, lưu sự cố. Trả về (frame đã thu nhỏ, frame đã vẽ)."""
        frame = self._resize(raw_frame)
        scale = raw_frame.shape[1] / frame.shape[1]
        annotated = frame.copy()
        try:
            pose_results = self.pose_model.track(
                frame, persist=True, conf=self.POSE_CONF_LOW, imgsz=self.PROCESS_WIDTH,
                tracker=self.tracker_cfg, verbose=False)
            self._run_object_models(frame)

            texts = []   # chữ tiếng Việt có dấu, vẽ bằng Pillow (chỉ khi có cảnh báo/vật thể)
            obj_dets = self._draw_objects(annotated, frame, texts)
            persons, events = self._process_persons(pose_results, annotated, texts)
            if texts:
                draw_texts_vi(annotated, texts)

            # Chỉ xét vật đủ tin cậy (ngưỡng riêng từng loại), rồi gán cho thí sinh gần nhất
            obj_alerts = [d for d in obj_dets if d[1] >= Config.ALERT_MIN_CONF.get(d[0], 0.0)]
            hand_kinds = ("mobile_phone",) if Config.PHONE_REQUIRE_HAND else ()
            events += assign_objects(obj_alerts, persons, hand_kinds=hand_kinds, hand_radius=Config.PHONE_HAND_RADIUS)

            # Chỉ lưu khi hành vi kéo dài liên tục đủ lâu (giảm báo sai / trùng lặp)
            now = self._clock()
            ready = self.sustain.ready({(s, w) for s, w, _, _ in events if s is not None}, now)
            for seat, warning, conf, bbox in events:
                if (seat, warning) in ready:
                    self.recorder.save(raw_frame, scale, seat, warning, conf, bbox, now)
        except Exception as e:
            print(f"[MonitoringService] Inference Error: {e}")
        return frame, annotated

    def _process_loop(self):
        print("[MonitoringService] Loop started processing frames with ensemble models...")
        while self.is_running:
            try:
                success, raw_frame = self._next_frame()
                if not success or raw_frame is None:
                    time.sleep(0.01)
                    continue

                frame, annotated = self._process_frame(raw_frame)

                # Ghi nhớ các nét vẽ cảnh báo để phủ lên video gốc (video hiển thị mượt)
                mask = (annotated != frame).any(axis=2)
                with self.lock:
                    self.latest_frame = annotated
                    self.overlay_mask = mask

                self._fps_n += 1
                if time.time() - self._fps_t >= 3:
                    self.fps = self._fps_n / (time.time() - self._fps_t)
                    self._fps_t = time.time()
                    self._fps_n = 0
            except Exception as e:
                print(f"[MonitoringService] Error in process loop: {e}")
                time.sleep(0.05)

    def get_latest_frame(self):
        with self.lock:
            annotated = self.latest_frame
            mask = self.overlay_mask

        # File video: hiển thị frame đã xử lý
        if not self.use_reader:
            return annotated.copy() if annotated is not None else None

        # Cam trực tiếp: hiển thị frame mới nhất của cam (mượt) + phủ khung cảnh báo của lần AI gần nhất
        with self._raw_lock:
            raw = self._raw_frame
        if raw is None:
            return annotated.copy() if annotated is not None else None
        out = self._resize(raw).copy()
        if annotated is not None and mask is not None and out.shape == annotated.shape:
            out[mask] = annotated[mask]
        return out
