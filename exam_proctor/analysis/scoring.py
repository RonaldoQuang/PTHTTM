"""
analysis/scoring.py
-------------------
Điểm nghi ngờ của từng thí sinh: mỗi sự cố cộng điểm theo trọng số, điểm giảm dần theo thời gian,
và thí sinh bị gắn cờ khi vượt ngưỡng (ngưỡng đọc từ trang Cài đặt, mặc định lấy trong config).
"""
from config.config import Config


class ScoreKeeper:
    def __init__(self, db=None):
        self.db = db
        self._scores = {}   # số chỗ -> (điểm, thời điểm cập nhật cuối)

    def reset(self):
        self._scores = {}

    @staticmethod
    def delta(warning):
        """Điểm cộng cho 1 loại cảnh báo (trọng số trong Config.SCORE_WEIGHTS)."""
        key = str(warning).strip().lower().replace(" ", "_")
        return Config.SCORE_WEIGHTS.get(key, 1)

    def threshold(self):
        try:
            row = self.db.fetch_one("SELECT value FROM system_settings WHERE key = 'suspicion_threshold'")
            if row and row["value"] not in (None, ""):
                return float(row["value"])
        except Exception:
            pass
        return float(Config.SUSPICION_ALERT_THRESHOLD)

    def add(self, seat, delta, now):
        """Cộng điểm (có giảm dần theo thời gian) và trả về (điểm mới, 'flagged'/'active')."""
        score, ts = self._scores.get(seat, (0.0, now))
        score = max(0.0, score - Config.SCORE_DECAY_PER_MINUTE * (now - ts) / 60.0) + delta
        self._scores[seat] = (score, now)
        return score, ("flagged" if score >= self.threshold() else "active")
