# """
# analysis/activity_analyzer.py
# -------------------------------
# The "brain" of the system. For every processed frame it receives:
#   - the list of confirmed Track objects (tracking.tracker.Track)
#   - the list of phone Detections from detection.detector
#   - the raw frame (for cropping regions to run head-pose on)

# ...and produces a list of Incident dicts for any behavior rule that
# fired this frame, after applying per-track state machines (sustained
# frames/seconds, cooldowns) so single noisy frames don't spam alerts.

# Design note: all thresholds live in config/config.py. This class is
# intentionally stateful (keeps a per-track history) but pure Python /
# NumPy so it has no external side effects (no DB writes) - the caller
# (dashboard/monitoring loop) is responsible for persisting incidents
# and screenshots via the reports/incidents modules.
# """

# import time
# from dataclasses import dataclass, field
# from typing import List, Optional

# from config.config import Config
# from analysis.head_pose import HeadPoseEstimator


# @dataclass
# class TrackState:
#     """Per-student rolling state used to decide when an event "sustains"
#     long enough to be worth logging, rather than firing every frame."""
#     consecutive_turn_frames: int = 0
#     face_missing_since: Optional[float] = None
#     seat_baseline_bbox: Optional[tuple] = None
#     away_from_seat_since: Optional[float] = None
#     standing_flagged: bool = False
#     proximity_since: dict = field(default_factory=dict)  # other_track_id -> ts


# @dataclass
# class Incident:
#     """A single suspicious-activity finding for one student in one frame."""
#     track_id: int
#     incident_type: str
#     confidence: float
#     description: str


# class ActivityAnalyzer:
#     """Applies rule-based suspicious-activity detection over tracked students."""

#     def __init__(self):
#         self.head_pose = HeadPoseEstimator()
#         self._states: dict[int, TrackState] = {}

#     def _state_for(self, track_id: int) -> TrackState:
#         if track_id not in self._states:
#             self._states[track_id] = TrackState()
#         return self._states[track_id]

#     def analyze(self, frame, tracks: list, phone_detections: list) -> List[Incident]:
#         """Run all rules for the current frame and return newly fired incidents."""
#         incidents: List[Incident] = []
#         now = time.time()

#         for track in tracks:
#             state = self._state_for(track.track_id)
#             x1, y1, x2, y2 = track.bbox
#             x1, y1 = max(0, x1), max(0, y1)
#             crop = frame[y1:y2, x1:x2]

#             incidents += self._check_head_turn(track, state, crop, now)
#             incidents += self._check_standing(track, state)
#             incidents += self._check_left_seat(track, state, now)
#             incidents += self._check_mobile_phone(track, phone_detections)

#         incidents += self._check_proximity_and_passing(tracks, phone_detections, now)

#         # Clean up state for tracks that no longer exist
#         active_ids = {t.track_id for t in tracks}
#         for stale_id in list(self._states.keys()):
#             if stale_id not in active_ids:
#                 del self._states[stale_id]

#         return incidents

#     # ------------------------------------------------------------- rules
#     def _check_head_turn(self, track, state: TrackState, crop, now: float) -> List[Incident]:
#         pose = self.head_pose.estimate(crop)
#         results = []

#         if not pose["face_found"]:
#             if state.face_missing_since is None:
#                 state.face_missing_since = now
#             elif now - state.face_missing_since >= Config.FACE_MISSING_SECONDS_THRESHOLD:
#                 results.append(Incident(
#                     track_id=track.track_id,
#                     incident_type="face_not_visible",
#                     confidence=0.6,
#                     description=f"Face not visible for over {Config.FACE_MISSING_SECONDS_THRESHOLD}s",
#                 ))
#                 state.face_missing_since = now  # reset so it doesn't spam every frame
#             state.consecutive_turn_frames = 0
#             return results

#         state.face_missing_since = None

#         if abs(pose["yaw"]) >= Config.HEAD_TURN_YAW_THRESHOLD:
#             state.consecutive_turn_frames += 1
#             if state.consecutive_turn_frames == Config.HEAD_TURN_SUSTAIN_FRAMES:
#                 direction = "left" if pose["yaw"] > 0 else "right"
#                 results.append(Incident(
#                     track_id=track.track_id,
#                     incident_type="looking_away",
#                     confidence=min(0.95, 0.5 + abs(pose["yaw"]) / 90),
#                     description=f"Sustained head turn to the {direction} ({pose['yaw']:.1f} deg)",
#                 ))
#         else:
#             state.consecutive_turn_frames = 0

#         return results

#     def _check_standing(self, track, state: TrackState) -> List[Incident]:
#         results = []
#         if track.baseline_height is None:
#             return results

#         current_height = track.bbox[3] - track.bbox[1]
#         growth_ratio = (current_height - track.baseline_height) / track.baseline_height

#         if growth_ratio >= Config.STANDING_HEIGHT_RATIO_DELTA and not state.standing_flagged:
#             state.standing_flagged = True
#             results.append(Incident(
#                 track_id=track.track_id,
#                 incident_type="standing",
#                 confidence=0.7,
#                 description="Bounding-box height increase suggests student stood up",
#             ))
#         elif growth_ratio < Config.STANDING_HEIGHT_RATIO_DELTA * 0.5:
#             state.standing_flagged = False  # sat back down, allow re-trigger later

#         return results

#     def _check_left_seat(self, track, state: TrackState, now: float) -> List[Incident]:
#         """Uses the tracker's own missed_frames as a proxy for "gone from seat"
#         (a confirmed track that starts missing frames but hasn't expired yet)."""
#         results = []
#         if track.missed_frames > 0:
#             if state.away_from_seat_since is None:
#                 state.away_from_seat_since = now
#             elif now - state.away_from_seat_since >= Config.SEAT_LEAVE_ABSENCE_SECONDS:
#                 results.append(Incident(
#                     track_id=track.track_id,
#                     incident_type="left_seat",
#                     confidence=0.65,
#                     description=f"Student absent from frame for over {Config.SEAT_LEAVE_ABSENCE_SECONDS}s",
#                 ))
#                 state.away_from_seat_since = now
#         else:
#             state.away_from_seat_since = None
#         return results

#     def _check_mobile_phone(self, track, phone_detections: list) -> List[Incident]:
#         results = []
#         tx1, ty1, tx2, ty2 = track.bbox
#         for phone in phone_detections:
#             px, py = phone.center
#             if tx1 - 20 <= px <= tx2 + 20 and ty1 - 20 <= py <= ty2 + 20:
#                 results.append(Incident(
#                     track_id=track.track_id,
#                     incident_type="mobile_phone",
#                     confidence=phone.confidence,
#                     description="Mobile phone detected within student's bounding box",
#                 ))
#         return results

#     def _check_proximity_and_passing(self, tracks: list, phone_detections: list, now: float) -> List[Incident]:
#         """Best-effort: flags sustained close proximity between two students
#         as 'close_interaction', and additionally as 'object_passing' if a
#         small (phone-sized) detection briefly appears between them - this
#         is a heuristic, not a definitive object-passing detector."""
#         results = []
#         for i in range(len(tracks)):
#             for j in range(i + 1, len(tracks)):
#                 t1, t2 = tracks[i], tracks[j]
#                 dist = self._bbox_distance(t1.bbox, t2.bbox)
#                 if dist <= Config.PROXIMITY_DISTANCE_PX:
#                     state1 = self._state_for(t1.track_id)
#                     key = t2.track_id
#                     if key not in state1.proximity_since:
#                         state1.proximity_since[key] = now
#                     elif now - state1.proximity_since[key] >= Config.PROXIMITY_SUSTAIN_SECONDS:
#                         results.append(Incident(
#                             track_id=t1.track_id,
#                             incident_type="close_interaction",
#                             confidence=0.5,
#                             description=f"Sustained close proximity to student #{t2.track_id}",
#                         ))
#                         # Best-effort object passing: an unassigned small object
#                         # detection sitting between the two students' boxes.
#                         midpoint = self._midpoint(t1.bbox, t2.bbox)
#                         for det in phone_detections:
#                             if self._point_near(det.center, midpoint, radius=60):
#                                 results.append(Incident(
#                                     track_id=t1.track_id,
#                                     incident_type="object_passing",
#                                     confidence=0.4,
#                                     description=f"Possible object passed between #{t1.track_id} and #{t2.track_id}",
#                                 ))
#                         state1.proximity_since[key] = now
#                 else:
#                     state1 = self._state_for(t1.track_id)
#                     state1.proximity_since.pop(t2.track_id, None)
#         return results

#     @staticmethod
#     def _bbox_distance(box_a, box_b) -> float:
#         ax = (box_a[0] + box_a[2]) / 2
#         ay = (box_a[1] + box_a[3]) / 2
#         bx = (box_b[0] + box_b[2]) / 2
#         by = (box_b[1] + box_b[3]) / 2
#         return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

#     @staticmethod
#     def _midpoint(box_a, box_b):
#         ax = (box_a[0] + box_a[2]) / 2
#         ay = (box_a[1] + box_a[3]) / 2
#         bx = (box_b[0] + box_b[2]) / 2
#         by = (box_b[1] + box_b[3]) / 2
#         return ((ax + bx) / 2, (ay + by) / 2)

#     @staticmethod
#     def _point_near(point, target, radius: float) -> bool:
#         return ((point[0] - target[0]) ** 2 + (point[1] - target[1]) ** 2) ** 0.5 <= radius

#     def close(self):
#         self.head_pose.close()


"""
analysis/activity_analyzer.py
-------------------------------
The "brain" of the system. For every processed frame it receives:
  - the list of confirmed Track objects (tracking.tracker.Track)
  - the list of custom object Detections (phone, laptop, cheat_paper)
  - the raw frame (for cropping regions to run head-pose on)

...and produces a list of Incident dicts for any behavior rule that
fired this frame.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional

from config.config import Config
from analysis.head_pose import HeadPoseEstimator


@dataclass
class TrackState:
    """Per-student rolling state used to decide when an event "sustains"
    long enough to be worth logging, rather than firing every frame."""
    consecutive_turn_frames: int = 0
    face_missing_since: Optional[float] = None
    seat_baseline_bbox: Optional[tuple] = None
    away_from_seat_since: Optional[float] = None
    standing_flagged: bool = False
    proximity_since: dict = field(default_factory=dict)  # other_track_id -> ts


@dataclass
class Incident:
    """A single suspicious-activity finding for one student in one frame."""
    track_id: int
    incident_type: str
    confidence: float
    description: str


class ActivityAnalyzer:
    """Applies rule-based suspicious-activity detection over tracked students."""

    def __init__(self):
        self.head_pose = HeadPoseEstimator()
        self._states: dict[int, TrackState] = {}

    def _state_for(self, track_id: int) -> TrackState:
        if track_id not in self._states:
            self._states[track_id] = TrackState()
        return self._states[track_id]

    def analyze(self, frame, tracks: list, custom_objects: list) -> List[Incident]:
        """Run all rules for the current frame and return newly fired incidents.
        
        Args:
            frame: Khung hình gốc từ Camera.
            tracks: Danh sách học sinh đang được theo dõi.
            custom_objects: Danh sách vật thể phát hiện từ model phao thi & thiết bị (phone, laptop, paper).
        """
        incidents: List[Incident] = []
        now = time.time()

        for track in tracks:
            state = self._state_for(track.track_id)
            x1, y1, x2, y2 = track.bbox
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(frame.shape[1], int(x2)), min(frame.shape[0], int(y2))
            
            # Crop vùng cá nhân để kiểm tra Pose/Head turn
            crop = frame[y1:y2, x1:x2]

            incidents += self._check_head_turn(track, state, crop, now)
            incidents += self._check_standing(track, state)
            incidents += self._check_left_seat(track, state, now)
            
            # Kiểm tra vật thể vi phạm trong vùng của thí sinh (phao thi, điện thoại, laptop)
            incidents += self._check_prohibited_objects(track, custom_objects)

        incidents += self._check_proximity_and_passing(tracks, custom_objects, now)

        # Dọn dẹp trạng thái của các track đã biến mất
        active_ids = {t.track_id for t in tracks}
        for stale_id in list(self._states.keys()):
            if stale_id not in active_ids:
                del self._states[stale_id]

        return incidents

    # ------------------------------------------------------------- rules
    def _check_head_turn(self, track, state: TrackState, crop, now: float) -> List[Incident]:
        if crop.size == 0:
            return []
            
        pose = self.head_pose.estimate(crop)
        results = []

        if not pose["face_found"]:
            if state.face_missing_since is None:
                state.face_missing_since = now
            elif now - state.face_missing_since >= Config.FACE_MISSING_SECONDS_THRESHOLD:
                results.append(Incident(
                    track_id=track.track_id,
                    incident_type="face_not_visible",
                    confidence=0.6,
                    description=f"Face not visible for over {Config.FACE_MISSING_SECONDS_THRESHOLD}s",
                ))
                state.face_missing_since = now
            state.consecutive_turn_frames = 0
            return results

        state.face_missing_since = None

        if abs(pose["yaw"]) >= Config.HEAD_TURN_YAW_THRESHOLD:
            state.consecutive_turn_frames += 1
            if state.consecutive_turn_frames == Config.HEAD_TURN_SUSTAIN_FRAMES:
                direction = "left" if pose["yaw"] > 0 else "right"
                results.append(Incident(
                    track_id=track.track_id,
                    incident_type="looking_away",
                    confidence=min(0.95, 0.5 + abs(pose["yaw"]) / 90),
                    description=f"Sustained head turn to the {direction} ({pose['yaw']:.1f} deg)",
                ))
        else:
            state.consecutive_turn_frames = 0

        return results

    def _check_standing(self, track, state: TrackState) -> List[Incident]:
        results = []
        if track.baseline_height is None:
            return results

        current_height = track.bbox[3] - track.bbox[1]
        growth_ratio = (current_height - track.baseline_height) / track.baseline_height

        if growth_ratio >= Config.STANDING_HEIGHT_RATIO_DELTA and not state.standing_flagged:
            state.standing_flagged = True
            results.append(Incident(
                track_id=track.track_id,
                incident_type="standing",
                confidence=0.7,
                description="Bounding-box height increase suggests student stood up",
            ))
        elif growth_ratio < Config.STANDING_HEIGHT_RATIO_DELTA * 0.5:
            state.standing_flagged = False

        return results

    def _check_left_seat(self, track, state: TrackState, now: float) -> List[Incident]:
        results = []
        if track.missed_frames > 0:
            if state.away_from_seat_since is None:
                state.away_from_seat_since = now
            elif now - state.away_from_seat_since >= Config.SEAT_LEAVE_ABSENCE_SECONDS:
                results.append(Incident(
                    track_id=track.track_id,
                    incident_type="left_seat",
                    confidence=0.65,
                    description=f"Student absent from frame for over {Config.SEAT_LEAVE_ABSENCE_SECONDS}s",
                ))
                state.away_from_seat_since = now
        else:
            state.away_from_seat_since = None
        return results

    def _check_prohibited_objects(self, track, custom_objects: list) -> List[Incident]:
        """Phát hiện phao thi, điện thoại, hoặc laptop nằm trong/gần bounding box của học sinh."""
        results = []
        tx1, ty1, tx2, ty2 = track.bbox
        margin = 30  # Mở rộng vùng kiểm tra xung quanh thí sinh

        for obj in custom_objects:
            px, py = obj.center
            if tx1 - margin <= px <= tx2 + margin and ty1 - margin <= py <= ty2 + margin:
                
                # Phân loại hành vi vi phạm dựa trên label vật thể
                if obj.label in ["cheat_paper", "paper"]:
                    results.append(Incident(
                        track_id=track.track_id,
                        incident_type="cheat_paper",
                        confidence=obj.confidence,
                        description="Unauthorized notes/cheat paper detected near student",
                    ))
                elif obj.label in ["mobile_phone", "phone", "cell phone"]:
                    results.append(Incident(
                        track_id=track.track_id,
                        incident_type="mobile_phone",
                        confidence=obj.confidence,
                        description="Mobile phone detected near student",
                    ))
                elif obj.label in ["laptop"]:
                    results.append(Incident(
                        track_id=track.track_id,
                        incident_type="laptop",
                        confidence=obj.confidence,
                        description="Unauthorized electronic device (laptop) detected",
                    ))
        return results

    def _check_proximity_and_passing(self, tracks: list, custom_objects: list, now: float) -> List[Incident]:
        """Phát hiện khoảng cách quá gần giữa 2 học sinh và nghi vấn truyền đồ vật/phao thi."""
        results = []
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                t1, t2 = tracks[i], tracks[j]
                dist = self._bbox_distance(t1.bbox, t2.bbox)
                if dist <= Config.PROXIMITY_DISTANCE_PX:
                    state1 = self._state_for(t1.track_id)
                    key = t2.track_id
                    if key not in state1.proximity_since:
                        state1.proximity_since[key] = now
                    elif now - state1.proximity_since[key] >= Config.PROXIMITY_SUSTAIN_SECONDS:
                        results.append(Incident(
                            track_id=t1.track_id,
                            incident_type="close_interaction",
                            confidence=0.5,
                            description=f"Sustained close proximity to student #{t2.track_id}",
                        ))
                        
                        # Kiểm tra xem có vật thể nhỏ (phao/điện thoại) giữa 2 người không
                        midpoint = self._midpoint(t1.bbox, t2.bbox)
                        for obj in custom_objects:
                            if self._point_near(obj.center, midpoint, radius=60):
                                results.append(Incident(
                                    track_id=t1.track_id,
                                    incident_type="object_passing",
                                    confidence=0.6,
                                    description=f"Possible object passing ({obj.label}) between #{t1.track_id} and #{t2.track_id}",
                                ))
                        state1.proximity_since[key] = now
                else:
                    state1 = self._state_for(t1.track_id)
                    state1.proximity_since.pop(t2.track_id, None)
        return results

    @staticmethod
    def _bbox_distance(box_a, box_b) -> float:
        ax = (box_a[0] + box_a[2]) / 2
        ay = (box_a[1] + box_a[3]) / 2
        bx = (box_b[0] + box_b[2]) / 2
        by = (box_b[1] + box_b[3]) / 2
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    @staticmethod
    def _midpoint(box_a, box_b):
        ax = (box_a[0] + box_a[2]) / 2
        ay = (box_a[1] + box_a[3]) / 2
        bx = (box_b[0] + box_b[2]) / 2
        by = (box_b[1] + box_b[3]) / 2
        return ((ax + bx) / 2, (ay + by) / 2)

    @staticmethod
    def _point_near(point, target, radius: float) -> bool:
        return ((point[0] - target[0]) ** 2 + (point[1] - target[1]) ** 2) ** 0.5 <= radius

    def close(self):
        self.head_pose.close()