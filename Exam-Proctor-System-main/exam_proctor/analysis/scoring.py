"""
analysis/scoring.py
---------------------
Rule-based suspicion scoring engine. Keeps a running score per student
track, applies configured weights when incidents are reported, and
slowly decays the score over time so a single old event doesn't
permanently flag a student.

Important: this system NEVER claims to detect "cheating" directly.
It only aggregates a suspicion score from observed behaviors; a human
invigilator must review any flagged student before drawing conclusions.
"""

import time
from config.config import Config


class ScoringEngine:
    """Tracks and updates suspicion scores for every student track."""

    def __init__(self, weights: dict = None, threshold: float = None, decay_per_minute: float = None):
        self.weights = weights or Config.SCORE_WEIGHTS
        self.threshold = threshold or Config.SUSPICION_ALERT_THRESHOLD
        self.decay_per_minute = decay_per_minute if decay_per_minute is not None else Config.SCORE_DECAY_PER_MINUTE

        # track_id -> {"score": float, "last_update": ts, "last_event_ts": {event_type: ts}}
        self._state: dict[int, dict] = {}

    def _get_state(self, track_id: int):
        if track_id not in self._state:
            self._state[track_id] = {
                "score": 0.0,
                "last_update": time.time(),
                "last_event_ts": {},
            }
        return self._state[track_id]

    def _apply_decay(self, state: dict):
        now = time.time()
        minutes_elapsed = (now - state["last_update"]) / 60.0
        if minutes_elapsed > 0:
            state["score"] = max(0.0, state["score"] - minutes_elapsed * self.decay_per_minute)
            state["last_update"] = now

    def register_event(self, track_id: int, event_type: str) -> dict:
        """
        Apply a cooldown-gated score increment for `event_type` on the
        given track. Returns a dict describing whether the event was
        accepted (i.e. not suppressed by cooldown), the score delta
        applied, the new total score, and whether the alert threshold
        was crossed on this call.
        """
        state = self._get_state(track_id)
        self._apply_decay(state)

        now = time.time()
        last_fired = state["last_event_ts"].get(event_type, 0)
        if now - last_fired < Config.EVENT_COOLDOWN_SECONDS:
            return {"accepted": False, "delta": 0, "score": state["score"], "crossed_threshold": False}

        was_below = state["score"] < self.threshold
        delta = self.weights.get(event_type, 1)
        state["score"] += delta
        state["last_event_ts"][event_type] = now
        crossed = was_below and state["score"] >= self.threshold

        return {
            "accepted": True,
            "delta": delta,
            "score": state["score"],
            "crossed_threshold": crossed,
        }

    def get_score(self, track_id: int) -> float:
        state = self._get_state(track_id)
        self._apply_decay(state)
        return state["score"]

    def is_flagged(self, track_id: int) -> bool:
        return self.get_score(track_id) >= self.threshold

    def reset_track(self, track_id: int):
        self._state.pop(track_id, None)

    def reset_all(self):
        self._state = {}
