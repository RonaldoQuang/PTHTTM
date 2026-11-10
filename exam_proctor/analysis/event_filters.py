"""
analysis/event_filters.py
-------------------------
Hai bộ lọc giúp giảm báo sai:
  - SustainFilter: chỉ ghi nhận hành vi khi nó kéo dài LIÊN TỤC đủ lâu (lọc nhiễu 1 frame).
  - assign_objects: gán vật thể bị cấm (điện thoại/phao/laptop) cho thí sinh gần nhất.
"""
import math

OBJECT_TYPES = ("mobile_phone", "cheat_paper", "laptop")


class SustainFilter:
    def __init__(self, pose_sustain=2.0, object_sustain=1.0):
        self.pose_sustain = pose_sustain       # giây hành vi tư thế phải kéo dài liên tục
        self.object_sustain = object_sustain   # giây vật thể phải xuất hiện liên tục
        self._pending = {}                     # (số chỗ, hành vi) -> thời điểm bắt đầu

    def reset(self):
        self._pending = {}

    def ready(self, active_keys, now):
        """active_keys: tập (số chỗ, hành vi) đang xảy ra ở frame này. Trả về tập đã kéo dài đủ lâu."""
        self._pending = {k: self._pending.get(k, now) for k in active_keys}
        ready = set()
        for k, t0 in self._pending.items():
            need = self.object_sustain if k[1] in OBJECT_TYPES else self.pose_sustain
            if now - t0 >= need:
                ready.add(k)
        return ready


def assign_objects(obj_dets, persons, margin=0.2, hand_kinds=(), hand_radius=0.3):
    """obj_dets: [(loại, conf, bbox vật)], persons: [(số chỗ, bbox người[, danh sách cổ tay (x, y)])].
    Trả về [(số chỗ, loại, conf, bbox người)] cho vật có tâm nằm trong/sát khung của một người.
    Với các loại trong hand_kinds, vật còn phải nằm trong hand_radius * chiều cao người quanh một cổ tay
    (người không có cổ tay nào thấy rõ thì không nhận vật đó)."""
    events = []
    for kind, oconf, (ox1, oy1, ox2, oy2) in obj_dets:
        ocx, ocy = (ox1 + ox2) / 2, (oy1 + oy2) / 2
        best, best_d = None, None
        for person in persons:
            seat, (px1, py1, px2, py2) = person[0], person[1]
            hands = person[2] if len(person) > 2 else None
            mx, my = (px2 - px1) * margin, (py2 - py1) * margin
            if not (px1 - mx <= ocx <= px2 + mx and py1 - my <= ocy <= py2 + my):
                continue
            if kind in hand_kinds and hands is not None:
                limit = hand_radius * (py2 - py1)
                if not any(math.hypot(ocx - hx, ocy - hy) <= limit for hx, hy in hands):
                    continue
            d = math.hypot(ocx - (px1 + px2) / 2, ocy - (py1 + py2) / 2)
            if best_d is None or d < best_d:
                best, best_d = (seat, (px1, py1, px2, py2)), d
        if best is not None:
            events.append((best[0], kind, oconf, best[1]))
    return events
