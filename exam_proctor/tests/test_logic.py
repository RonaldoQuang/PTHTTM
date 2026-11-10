"""Test tự động cho các module logic (không cần camera/model). Chạy:  python -m pytest tests -q"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.event_filters import SustainFilter, assign_objects
from analysis.pose_rules import analyze_pose_warnings, calculate_angle, pick_main_warning
from analysis.scoring import ScoreKeeper
from tracking.seat_mapper import SeatMapper


def make_kpts(over=None):
    """17 keypoint ngồi bình thường nhìn thẳng, ghi đè từng điểm bằng over={chỉ_số:(x,y,conf)}."""
    k = np.zeros((17, 3), dtype=float)
    pts = {0: (100, 50), 1: (90, 45), 2: (110, 45), 3: (80, 50), 4: (120, 50),
           5: (70, 100), 6: (130, 100), 9: (60, 160), 10: (140, 160), 11: (80, 200), 12: (120, 200)}
    for i, (x, y) in pts.items():
        k[i] = (x, y, 0.9)
    for i, v in (over or {}).items():
        k[i] = v
    return k


# ---------------------------------------------------------------- luật tư thế
def test_normal_posture_has_no_warning():
    assert analyze_pose_warnings(make_kpts(), box=(40, 30, 160, 170)) == []


def test_head_turn_detected_when_nose_near_one_eye():
    k = make_kpts({0: (91, 50, 0.9)})        # mũi sát mắt trái
    assert "QUAY DAU" in analyze_pose_warnings(k, box=(40, 30, 160, 170))


def test_standing_needs_legs_or_very_tall_box():
    legs = {13: (80, 260, 0.9), 14: (120, 260, 0.9), 15: (80, 320, 0.9), 16: (120, 320, 0.9)}
    assert "DUNG DAY" in analyze_pose_warnings(make_kpts(legs), box=(60, 0, 140, 160))    # cao/rộng 2.0 + thấy chân
    assert "DUNG DAY" not in analyze_pose_warnings(make_kpts(), box=(60, 0, 140, 160))    # cao/rộng 2.0, không thấy chân
    assert "DUNG DAY" in analyze_pose_warnings(make_kpts(), box=(60, 0, 100, 200))        # khung rất cao (5.0)


def test_raised_hand_when_wrist_above_eye():
    k = make_kpts({9: (60, 20, 0.9)})
    assert "GIO TAY CAO" in analyze_pose_warnings(k, box=(40, 30, 160, 170))


def test_face_lost_with_shoulders_visible_is_bowing_face():
    k = make_kpts({0: (100, 50, 0.0), 1: (90, 45, 0.0), 2: (110, 45, 0.0)})
    assert "CUI GAM MAT" in analyze_pose_warnings(k, box=(40, 30, 160, 170))


def test_priority_prefers_standing_over_head_turn():
    assert pick_main_warning(["QUAY DAU", "DUNG DAY"]) == "DUNG DAY"
    assert pick_main_warning([]) is None


def test_angle_returns_none_for_low_confidence():
    assert calculate_angle((0, 0, 0.0), (1, 0, 0.9), (1, 1, 0.9)) is None
    assert round(calculate_angle((0, 1, 0.9), (0, 0, 0.9), (1, 0, 0.9))) == 90


# ---------------------------------------------------------------- chỗ ngồi
def test_new_tracker_id_at_same_position_keeps_same_seat():
    m = SeatMapper()
    m.begin_frame(); a = m.assign(5, (100, 100, 200, 300)); b = m.assign(6, (300, 100, 400, 300))
    m.begin_frame(); m.assign(5, (102, 100, 202, 300)); b2 = m.assign(6, (300, 100, 400, 300))
    m.begin_frame(); b3 = m.assign(77, (298, 102, 398, 302))   # ID 6 bị đổi thành 77
    assert (a, b) == (1, 2) and b2 == 2 and b3 == 2
    assert m.count == 2


def test_person_at_new_position_gets_new_seat_and_none_id_ignored():
    m = SeatMapper(); m.begin_frame()
    m.assign(1, (100, 100, 200, 300))
    assert m.assign(2, (700, 100, 800, 300)) == 2
    assert m.assign(None, (1, 1, 2, 2)) is None


# ---------------------------------------------------------------- lọc hành vi
def test_sustain_requires_continuous_time():
    f = SustainFilter(pose_sustain=2.0, object_sustain=1.0)
    k = {(1, "QUAY DAU"), (2, "mobile_phone")}
    assert f.ready(k, 0.0) == set()
    assert f.ready(k, 1.2) == {(2, "mobile_phone")}
    assert f.ready({(1, "QUAY DAU")}, 2.5) == {(1, "QUAY DAU")}
    assert f.ready(set(), 3.0) == set()                       # biến mất -> đếm lại từ đầu
    assert f.ready({(1, "QUAY DAU")}, 3.5) == set()


def test_object_assigned_to_nearest_person_only_if_inside():
    persons = [(1, (0, 0, 100, 200)), (2, (300, 0, 400, 200))]
    ev = assign_objects([("mobile_phone", 0.9, (310, 90, 330, 110)),
                         ("laptop", 0.8, (600, 600, 650, 650))], persons)
    assert ev == [(2, "mobile_phone", 0.9, (300, 0, 400, 200))]


# ---------------------------------------------------------------- chấm điểm
def test_scoring_adds_flags_and_decays():
    s = ScoreKeeper(db=None)
    score, status = s.add(1, ScoreKeeper.delta("mobile_phone"), 0)
    assert score == 10 and status == "active"
    score, status = s.add(1, ScoreKeeper.delta("cheat_paper"), 0)
    assert score == 20 and status == "flagged"
    score, _ = s.add(1, 0, 600)                                # 10 phút sau: giảm 10 điểm
    assert score == 10


def test_unknown_warning_gets_default_weight_one():
    assert ScoreKeeper.delta("something_new") == 1


# ---------------------------------------------------------------- ghi sự cố theo "đợt"
def test_recorder_logs_one_incident_per_continuous_episode():
    from core.incident_recorder import IncidentRecorder
    r = IncidentRecorder(db=None, exam_id=0)
    assert r.should_record(1, "laptop", 0.0) is True            # bắt đầu đợt 1
    assert all(r.should_record(1, "laptop", t) is False for t in range(1, 40))   # vẫn đang diễn ra
    assert r.should_record(1, "laptop", 60.0) is True           # kéo dài quá 60s -> nhắc lại
    assert r.should_record(1, "laptop", 61.0) is False
    assert r.should_record(1, "laptop", 70.0) is True           # vắng >5s rồi xuất hiện lại = đợt mới
    assert r.should_record(2, "laptop", 70.0) is True           # thí sinh khác tính riêng


def test_phone_must_be_near_a_wrist_but_laptop_need_not():
    persons = [(1, (0, 0, 100, 200), [(50, 120)]),      # cổ tay ở (50,120)
               (2, (300, 0, 400, 200), [])]              # không thấy cổ tay nào
    near = ("mobile_phone", 0.5, (45, 110, 65, 130))      # sát cổ tay người 1
    far = ("mobile_phone", 0.5, (80, 10, 95, 25))         # nằm trong khung nhưng xa cổ tay
    hidden = ("mobile_phone", 0.5, (340, 100, 360, 120))  # người 2 không thấy cổ tay
    laptop = ("laptop", 0.9, (310, 100, 390, 150))
    ev = assign_objects([near, far, hidden, laptop], persons, hand_kinds=("mobile_phone",), hand_radius=0.3)
    assert [(e[0], e[1]) for e in ev] == [(1, "mobile_phone"), (2, "laptop")]
    # tắt luật cổ tay -> cả 4 vật đều được gán
    assert len(assign_objects([near, far, hidden, laptop], persons)) == 4


def test_file_playback_skips_frames_to_stay_real_time():
    import time
    import cv2
    from core.monitoring_service import MonitoringService
    from camera.camera_manager import CameraManager

    path = os.path.join(tempfile.mkdtemp(), "v.mp4")
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (64, 48))
    for _ in range(200):
        vw.write(np.zeros((48, 64, 3), dtype=np.uint8))
    vw.release()

    svc = MonitoringService.__new__(MonitoringService)       # không nạp model: chỉ test phần đọc video
    svc.camera_manager = CameraManager(source=path)
    assert svc.camera_manager.open()
    svc.REALTIME_FILE, svc._play_t0, svc._play_fps = True, None, 25.0
    t0 = time.time()
    n = 0
    while time.time() - t0 < 1.0:
        ok, _ = svc._next_file_frame()
        assert ok
        n += 1
        time.sleep(0.2)                                       # giả lập AI xử lý chậm: 5 frame/giây
    pos = svc.camera_manager.cap.get(cv2.CAP_PROP_POS_FRAMES)
    assert n <= 7 and 20 <= pos <= 32, (n, pos)               # sau ~1s thật, video đã phát ~25 frame (không phải ~5)
    svc.camera_manager.release()
