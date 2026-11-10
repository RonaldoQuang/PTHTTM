"""
tracking/seat_mapper.py
-----------------------
Đổi ID của tracker (hay bị đổi khi thí sinh bị che) thành SỐ CHỖ NGỒI ổn định theo vị trí.
Một ID mới xuất hiện ở đúng vị trí một chỗ cũ (chưa có ai khác ngồi trong frame này) sẽ dùng lại chỗ đó.
Giả định: camera cố định và thí sinh ngồi gần như một chỗ.
"""
import math


class SeatMapper:
    def __init__(self, x_tol=0.5, y_tol=0.6, smooth=0.05):
        self.x_tol = x_tol        # sai lệch ngang tối đa (tính theo bề rộng khung người)
        self.y_tol = y_tol        # sai lệch dọc tối đa (tính theo chiều cao khung người)
        self.smooth = smooth      # chỗ ngồi cập nhật chậm để không lệch khi người đứng dậy
        self.reset()

    def reset(self):
        self._seats = {}          # số chỗ -> (tâm x, tâm y, rộng, cao)
        self._seat_of_tid = {}    # ID tracker -> số chỗ
        self._next = 1
        self._used = set()

    @property
    def count(self):
        """Số chỗ ngồi (thí sinh) đã nhận diện."""
        return self._next - 1

    def begin_frame(self):
        """Gọi đầu mỗi frame để biết chỗ nào đã có người trong frame này."""
        self._used = set()

    def assign(self, tid, bbox):
        """Trả về số chỗ cho người có ID tracker `tid` ở khung `bbox` (None nếu tracker chưa có ID)."""
        if tid is None:
            return None
        x1, y1, x2, y2 = bbox
        cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
        seat = self._seat_of_tid.get(tid)
        if seat is None:
            best, best_d = None, None
            for sid, (ax, ay, aw, ah) in self._seats.items():
                if sid in self._used:
                    continue
                if abs(cx - ax) < self.x_tol * max(w, aw) and abs(cy - ay) < self.y_tol * max(h, ah):
                    d = math.hypot(cx - ax, cy - ay)
                    if best_d is None or d < best_d:
                        best, best_d = sid, d
            if best is None:
                best = self._next
                self._next += 1
                self._seats[best] = (cx, cy, w, h)
            seat = best
            self._seat_of_tid[tid] = seat
        self._used.add(seat)
        ax, ay, aw, ah = self._seats[seat]
        k = self.smooth
        self._seats[seat] = (ax + (cx - ax) * k, ay + (cy - ay) * k, aw + (w - aw) * k, ah + (h - ah) * k)
        return seat
