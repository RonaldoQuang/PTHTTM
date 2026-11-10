"""
core/incident_recorder.py
-------------------------
Ghi nhận sự cố: cooldown, cắt ảnh bằng chứng, ghi bảng incidents/student_tracks và cập nhật điểm nghi ngờ.
"""
import cv2

from analysis.scoring import ScoreKeeper
from utils.helpers import save_screenshot, incident_label, draw_texts_vi


def build_evidence(raw, scale, bbox, label):
    """Cắt vùng thí sinh vi phạm từ frame GỐC (độ phân giải cao), rồi vẽ lại khung đỏ và chữ cảnh báo."""
    h, w = raw.shape[:2]
    x1, y1, x2, y2 = [int(v * scale) for v in bbox]
    px = int((x2 - x1) * 0.15)
    py = int((y2 - y1) * 0.10)
    cx1 = max(0, x1 - px)
    cy1 = max(0, y1 - max(py, 40))              # chừa chỗ cho dòng chữ cảnh báo
    cx2 = min(w, max(x2 + px, x1 + 320))        # đủ rộng để không cắt mất chữ
    cy2 = min(h, y2 + py)
    crop = raw[cy1:cy2, cx1:cx2].copy()
    if crop.size == 0:
        return raw
    cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (0, 0, 255), max(2, int(round(2 * scale))))
    draw_texts_vi(crop, [(label, (x1 - cx1, max(22, y1 - cy1 - 10)), (0, 0, 255), 20)])
    return crop


class IncidentRecorder:
    # Mỗi "đợt" hành vi (liên tục, kể cả chớp tắt ngắn) chỉ ghi 1 sự cố, thay vì lặp lại mỗi 15 giây.
    EPISODE_GAP = 5.0       # giây vắng mặt để coi là kết thúc 1 đợt; xuất hiện lại sau đó = đợt mới
    REPEAT_AFTER = 60.0     # hành vi kéo dài liên tục quá lâu thì ghi nhắc lại sau từng khoảng này (giây)

    def __init__(self, db, exam_id, scorer=None):
        self.db = db
        self.exam_id = exam_id
        self.scorer = scorer or ScoreKeeper(db)
        self.last_saved = {}    # (số chỗ, hành vi) -> thời điểm ghi sự cố gần nhất
        self.last_active = {}   # (số chỗ, hành vi) -> lần cuối hành vi còn đang diễn ra

    def reset(self):
        self.last_saved = {}
        self.last_active = {}
        self.scorer.reset()

    def should_record(self, seat, warning, now):
        """True nếu đây là ĐỢT MỚI của hành vi (hoặc đã kéo dài quá REPEAT_AFTER giây kể từ lần ghi trước)."""
        key = (seat, warning)
        prev_active = self.last_active.get(key)
        self.last_active[key] = now
        last_saved = self.last_saved.get(key)
        if (last_saved is None or prev_active is None or now - prev_active > self.EPISODE_GAP
                or now - last_saved >= self.REPEAT_AFTER):
            self.last_saved[key] = now
            return True
        return False

    def save(self, raw, scale, seat, warning, conf=0.0, bbox=None, now=0.0):
        """Lưu ảnh bằng chứng + ghi 1 dòng vào incidents (có cooldown) + cập nhật điểm nghi ngờ."""
        if self.db is None or seat is None:
            return
        if not self.should_record(seat, warning, now):
            return
        try:
            # incidents.track_id là khóa ngoại -> student_tracks.id nên phải có track trước
            row = self.db.fetch_one(
                "SELECT id FROM student_tracks WHERE exam_id = ? AND tracker_id = ?", (self.exam_id, seat))
            if row:
                track_db_id = row["id"]
            else:
                track_db_id = self.db.execute(
                    "INSERT INTO student_tracks (exam_id, tracker_id, display_label) VALUES (?, ?, ?)",
                    (self.exam_id, seat, f"Chỗ #{seat}"))

            label = f"CẢNH BÁO: {incident_label(warning)}"
            evidence = build_evidence(raw, scale, bbox, label) if bbox is not None else raw
            path = save_screenshot(evidence, self.exam_id, seat, warning.replace(" ", "_"))
            delta = self.scorer.delta(warning)
            self.db.execute(
                """INSERT INTO incidents (exam_id, track_id, incident_type, confidence, score_delta, screenshot_path, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.exam_id, track_db_id, warning, conf, delta, path, f"Phát hiện: {incident_label(warning)}"))

            score, status = self.scorer.add(seat, delta, now)
            self.db.execute(
                "UPDATE student_tracks SET current_score = ?, status = ?, last_seen = datetime('now') WHERE id = ?",
                (round(score, 2), status, track_db_id))
        except Exception as e:
            print(f"[IncidentRecorder] Save incident error: {e}")
