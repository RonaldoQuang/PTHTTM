# AI-Based Offline Exam Cheating Detection System

A single-camera, AI-powered classroom exam proctoring web application.
It detects and tracks students with **YOLOv8**, estimates head pose with
**MediaPipe**, applies a **rule-based suspicion scoring system**, and gives
an invigilator a live **Flask + Bootstrap 5** dashboard with incident
logging, evidence screenshots, and PDF reports.

> **Important:** this system does **not** claim to definitively detect
> cheating. It flags *suspicious activity patterns* (looking away, phone
> use, standing, leaving the seat, close interaction, etc.) for a human
> invigilator to review. All incident types are logged with a confidence
> score and evidence screenshot so a person makes the final judgment.

---

## 1. Features

- **Single front-classroom camera** (webcam or IP/RTSP camera) — no extra hardware.
- **Student detection & tracking** — YOLOv8 person detection + a lightweight
  IoU multi-object tracker that keeps stable IDs across the exam (ByteTrack-style;
  see [Swapping the tracker](#7-swapping-in-official-bytetrack--deepsort) to use the official library instead).
- **Suspicious activity detection**:
  - Frequent head turning (left / right / back) via MediaPipe head-pose estimation
  - Standing up (bounding-box height heuristic)
  - Leaving the seat (sustained absence from frame)
  - Mobile phone detection (YOLOv8 "cell phone" class)
  - Multiple students in sustained close proximity
  - Best-effort object-passing heuristic between nearby students
  - Face not visible for an extended period
- **Rule-based suspicion scoring** with configurable weights, cooldowns, and
  time decay, so a student is only "flagged" after a pattern, not one frame.
- **Live dashboard**: MJPEG video stream, live stats, incident history with
  search/filter, Chart.js charts (incident types, daily trend).
- **PDF report export** per exam with student summary, incident log, and
  embedded evidence screenshots.
- **Admin authentication** with hashed passwords (Werkzeug PBKDF2/scrypt) and
  server-side sessions.
- **SQLite database** — zero external DB setup required.

---

## 2. Tech Stack

| Layer          | Technology                              |
|----------------|------------------------------------------|
| Backend        | Python 3.12+, Flask                       |
| Computer vision| OpenCV, Ultralytics YOLOv8, MediaPipe    |
| Tracking       | Custom IoU tracker (ByteTrack-style)      |
| Database       | SQLite                                    |
| Frontend       | HTML, CSS, Bootstrap 5, JavaScript, Chart.js |
| PDF reports    | fpdf2                                     |

---

## 3. Project Structure

```
exam_proctor/
├── app.py                      # Flask app factory / entry point
├── requirements.txt
├── config/
│   └── config.py               # ALL tunable thresholds & paths live here
├── database/
│   ├── schema.sql              # table definitions
│   └── db_manager.py           # DatabaseManager (connection + query helpers)
├── auth/
│   └── auth_manager.py         # AuthManager (hashing, login, password change)
├── camera/
│   └── camera_manager.py       # CameraManager (webcam / RTSP threaded capture)
├── detection/
│   ├── detection_types.py      # lightweight Detection dataclass (no heavy deps)
│   └── detector.py             # PersonPhoneDetector (YOLOv8 wrapper)
├── tracking/
│   └── tracker.py              # StudentTracker (IoU-based, ByteTrack-style)
├── analysis/
│   ├── head_pose.py            # MediaPipe-based yaw/pitch + face-visibility
│   ├── activity_analyzer.py    # rule engine -> Incident objects
│   └── scoring.py              # ScoringEngine (weights, cooldowns, decay)
├── core/
│   └── monitoring_service.py   # orchestrates the whole per-frame pipeline
├── reports/
│   └── report_generator.py     # PDF report builder (fpdf2)
├── web/                        # Flask blueprints (thin, no CV code here)
│   ├── auth_routes.py
│   ├── dashboard_routes.py
│   ├── monitor_routes.py
│   ├── report_routes.py
│   └── settings_routes.py
├── templates/                  # Jinja2 + Bootstrap 5 pages
├── static/
│   ├── css/style.css
│   ├── screenshots/            # saved evidence images
│   └── reports/                # generated PDF reports
├── models/                     # yolov8n.pt goes here (auto-downloaded)
└── utils/
    ├── logger.py
    └── helpers.py               # drawing, screenshot saving, JPEG encoding
```

This separation means: **web/ never touches OpenCV/YOLO/MediaPipe directly** —
it only calls `core.monitoring_service.MonitoringService`. This keeps the
pipeline testable in isolation and makes it easy to add a second camera or
swap models later without touching the Flask layer.

---

## 4. Installation

### Prerequisites
- Python 3.12+
- A webcam, or an IP camera with an RTSP/HTTP stream URL
- ~500 MB free disk space (YOLOv8n weights + MediaPipe models download on first run)

### Steps

```bash
# 1. Clone / unzip the project, then enter it
cd exam_proctor

# 2. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

The app starts at **http://localhost:5000**.

On first run, the SQLite database is created automatically at
`database/proctor.db` with a seeded default admin account:

```
Username: admin
Password: admin123
```

**Change this password immediately** from the Settings page after your first login.

The first time monitoring is started, Ultralytics will automatically download
`yolov8n.pt` (~6 MB) into the `models/` folder, and MediaPipe will download its
face-mesh model — both require an internet connection once.

---

## 5. Usage Guide

1. **Log in** with the admin credentials above.
2. Go to **Live Monitoring** → fill in the "Create Exam Session" form (name,
   subject, room, date/time) → **Create Exam**.
3. Under **Monitoring Controls**, select the exam you just created, optionally
   enter a camera source (leave blank for the default webcam, index `0`; or
   enter an RTSP/HTTP URL for an IP camera), then click **Start Monitoring**.
4. The live annotated feed appears with bounding boxes: green = normal,
   red = flagged (suspicion score over threshold), orange = detected phone.
5. Incidents are logged automatically as rules fire; view them under
   **Incidents** (with search/filter by exam, type, track ID, date range).
6. The **Dashboard** shows aggregate stats and charts.
7. Click **Stop Monitoring** when the exam ends.
8. Go to **Reports** → **Generate PDF** for the exam to produce a downloadable
   incident report with evidence screenshots.
9. Adjust the suspicion threshold, default camera source, and your password
   under **Settings**.

---

## 6. Database Schema

See `database/schema.sql` for the full DDL. Summary:

| Table            | Purpose                                                        |
|------------------|-----------------------------------------------------------------|
| `admin_users`    | Invigilator/admin accounts, hashed passwords, roles              |
| `exams`          | One row per exam session (name, room, date/time, status)        |
| `student_tracks` | One row per tracked student per exam (tracker id, score, status)|
| `incidents`      | One row per suspicious-activity event (type, confidence, screenshot, timestamp) |
| `reports`        | One row per generated PDF report                                 |
| `system_settings`| Key/value runtime settings (threshold, camera source)            |

---

## 7. Swapping in official ByteTrack / DeepSORT

`tracking/tracker.py` ships a small, dependency-free IoU tracker (inspired by
ByteTrack's match-then-recover approach) so the project has zero extra native
dependencies out of the box. To use the official implementations instead:

- **Ultralytics built-in ByteTrack**: replace `detector.detect()` +
  `tracker.update()` in `core/monitoring_service.py` with a single call to
  `model.track(frame, tracker="bytetrack.yaml", persist=True)`, which returns
  boxes with track IDs directly.
- **DeepSORT**: `pip install deep-sort-realtime`, then wrap it in a class with
  the same public method signature as `StudentTracker.update(detections) -> List[Track]`
  so nothing else in the codebase needs to change.

---

## 8. Configuration

All thresholds live in `config/config.py`, including:

- `YOLO_CONF_THRESHOLD`, `DEVICE` ('cpu' or 'cuda:0')
- `HEAD_TURN_YAW_THRESHOLD`, `HEAD_TURN_SUSTAIN_FRAMES`, `FACE_MISSING_SECONDS_THRESHOLD`
- `STANDING_HEIGHT_RATIO_DELTA`, `SEAT_LEAVE_ABSENCE_SECONDS`
- `PROXIMITY_DISTANCE_PX`, `PROXIMITY_SUSTAIN_SECONDS`
- `SCORE_WEIGHTS` (per incident type) and `SUSPICION_ALERT_THRESHOLD`

The suspicion threshold and camera source can also be changed at runtime from
the **Settings** page (stored in `system_settings`).

---

## 9. Testing Guide (no real classroom needed)

You don't need a live classroom to verify the system works end to end:

1. **Webcam smoke test**: run `python app.py`, start monitoring with camera
   source `0`, sit in front of your own webcam. Turn your head away for a
   couple of seconds — you should see a `looking_away` incident appear under
   **Incidents** within ~1–2 seconds. Hold a phone up — a `mobile_phone`
   incident should log almost immediately.
2. **Standing test**: stand up so your bounding box grows noticeably taller —
   a `standing` incident should log once.
3. **Leaving-seat test**: step out of frame for >10 seconds (configurable via
   `SEAT_LEAVE_ABSENCE_SECONDS`) — a `left_seat` incident should log.
4. **Multi-person test**: with a second person in frame, stand close together
   for a few seconds — a `close_interaction` incident should log for both.
5. **Sample/synthetic video**: if you don't have a webcam handy, you can point
   `CAMERA_SOURCE` at any local video file path (OpenCV can open video files
   the same way it opens a camera index), e.g. a short clip of people at desks,
   to exercise detection/tracking without live hardware.
6. **Unit-level checks**: the core modules (`tracking/tracker.py`,
   `analysis/scoring.py`, `database/db_manager.py`) have no OpenCV/YOLO
   dependency at import time except where noted, so you can write quick
   `pytest` unit tests against them directly, e.g.:

   ```python
   from tracking.tracker import StudentTracker
   from detection.detection_types import Detection

   def test_tracker_assigns_stable_ids():
       tracker = StudentTracker()
       det = Detection(0, "person", 0.9, 10, 10, 100, 200)
       for _ in range(5):
           tracks = tracker.update([det])
       assert len(tracks) == 1
       assert tracks[0].hits == 5
   ```

---

## 10. API Reference (internal JSON endpoints used by the dashboard)

All routes below require an authenticated session (redirect to `/login` otherwise).

| Method | Route                              | Description                                   |
|--------|-------------------------------------|------------------------------------------------|
| GET    | `/api/chart-data/incident-types`    | `{incident_type: count}` for the doughnut chart |
| GET    | `/api/chart-data/daily`             | `{labels: [...], counts: [...]}` last 14 days   |
| GET    | `/api/live-stats`                   | Live monitoring stats snapshot (or `{"active": false}`) |
| GET    | `/live/feed`                        | MJPEG stream (`multipart/x-mixed-replace`) of the annotated frame |
| GET    | `/live/status`                      | `{"running": true/false}`                       |
| POST   | `/live/create-exam`                 | Form fields: `exam_name, subject, room_name, exam_date, start_time, end_time` |
| POST   | `/live/start/<exam_id>`             | Form field: `camera_source` (optional)          |
| POST   | `/live/stop`                        | Stops the active monitoring session             |
| POST   | `/reports/generate/<exam_id>`       | Generates a PDF report, redirects to `/reports` |
| GET    | `/reports/download/<filename>`      | Downloads a generated PDF report                |

---

## 11. Known Limitations (be transparent with stakeholders)

- A single front camera cannot see what's on a student's desk, phone screen,
  or lap — it can only observe posture, gaze direction, and visible objects.
- Head-pose and "standing" heuristics are approximate; lighting, occlusion,
  and camera angle all affect accuracy. Confidence scores reflect this.
- The proximity/object-passing heuristic is explicitly best-effort and will
  have false positives (e.g., two students who are just sitting close together).
- This tool is a **decision-support aid for a human invigilator**, not an
  automated cheating verdict. Always review flagged incidents and screenshots
  manually before taking any action against a student.

---

## 12. License / Attribution

Built with Ultralytics YOLOv8 (AGPL-3.0 — check licensing terms for your use
case), Google MediaPipe (Apache 2.0), OpenCV (Apache 2.0), Flask (BSD-3-Clause),
and Bootstrap (MIT).
