"""
tracking/tracker.py
---------------------
A lightweight, dependency-free multi-object tracker inspired by
ByteTrack's core idea: match detections to existing tracks using IoU
+ a simple motion prediction, keep "lost" tracks alive for a grace
period (TRACK_MAX_AGE) so a student who is briefly occluded keeps the
same ID, and only prune tracks after they've been missing too long.

This module exposes a single class, `StudentTracker`, with a stable
public API (`update(detections) -> List[Track]`) so it can be swapped
for the official ByteTrack or DeepSORT implementation later without
changing any calling code (see README for how to do that swap).
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time

from config.config import Config


def iou(box_a, box_b) -> float:
    """Intersection-over-Union of two (x1, y1, x2, y2) boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter_area

    return inter_area / union if union > 0 else 0.0


@dataclass
class Track:
    """A single tracked student across frames."""
    track_id: int
    bbox: tuple
    confidence: float = 0.0
    age: int = 0                 # frames since creation
    missed_frames: int = 0       # consecutive frames without a match
    hits: int = 0                # total successful matches
    baseline_height: Optional[float] = None   # seated-height reference for standing detection
    last_seen_ts: float = field(default_factory=time.time)

    @property
    def is_confirmed(self) -> bool:
        return self.hits >= 2


class StudentTracker:
    """IoU-based tracker that assigns and maintains stable student IDs."""

    def __init__(self, max_age: int = None, iou_threshold: float = None):
        self.max_age = max_age or Config.TRACK_MAX_AGE
        self.iou_threshold = iou_threshold or Config.TRACK_MATCH_IOU_THRESHOLD
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, detections: List) -> List[Track]:
        """
        detections: list of Detection objects (from detection.detector)
        restricted to persons. Returns the list of currently active Tracks.
        """
        unmatched_dets = list(range(len(detections)))
        matched_track_ids = set()

        # Greedy IoU matching: for each existing track, find the best
        # unmatched detection above threshold.
        for track_id, track in self._tracks.items():
            best_iou = 0.0
            best_det_idx = None
            for det_idx in unmatched_dets:
                score = iou(track.bbox, detections[det_idx].bbox)
                if score > best_iou:
                    best_iou = score
                    best_det_idx = det_idx

            if best_det_idx is not None and best_iou >= self.iou_threshold:
                det = detections[best_det_idx]
                track.bbox = det.bbox
                track.confidence = det.confidence
                track.missed_frames = 0
                track.hits += 1
                track.age += 1
                track.last_seen_ts = time.time()
                if track.baseline_height is None and track.hits >= 5:
                    track.baseline_height = det.y2 - det.y1
                unmatched_dets.remove(best_det_idx)
                matched_track_ids.add(track_id)
            else:
                track.missed_frames += 1
                track.age += 1

        # Any detection left over becomes a brand-new track.
        for det_idx in unmatched_dets:
            det = detections[det_idx]
            new_track = Track(
                track_id=self._next_id,
                bbox=det.bbox,
                confidence=det.confidence,
                hits=1,
            )
            self._tracks[self._next_id] = new_track
            self._next_id += 1

        # Prune tracks that have been missing too long.
        expired = [tid for tid, t in self._tracks.items() if t.missed_frames > self.max_age]
        for tid in expired:
            del self._tracks[tid]

        return [t for t in self._tracks.values() if t.is_confirmed]

    def get_track(self, track_id: int) -> Optional[Track]:
        return self._tracks.get(track_id)

    def active_track_count(self) -> int:
        return len([t for t in self._tracks.values() if t.missed_frames == 0])

    def reset(self):
        self._tracks = {}
        self._next_id = 1
