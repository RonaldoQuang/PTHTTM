-- =====================================================================
-- schema.sql
-- SQLite schema for the AI Exam Proctoring System
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Admin / invigilator users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT DEFAULT 'invigilator',   -- 'admin' | 'invigilator'
    created_at      TEXT DEFAULT (datetime('now')),
    last_login      TEXT
);

-- ---------------------------------------------------------------------
-- Exams
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_name       TEXT NOT NULL,
    subject         TEXT,
    room_name       TEXT,
    exam_date       TEXT,
    start_time      TEXT,
    end_time        TEXT,
    status          TEXT DEFAULT 'scheduled',   -- scheduled | running | completed
    created_by      INTEGER REFERENCES admin_users(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- Student tracks (a "track" = one continuously tracked person id
-- for the duration of one exam session)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id         INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    tracker_id      INTEGER NOT NULL,          -- id assigned by ByteTrack/DeepSORT
    display_label   TEXT,                      -- e.g. "Student #4" or seat no.
    first_seen      TEXT DEFAULT (datetime('now')),
    last_seen       TEXT DEFAULT (datetime('now')),
    current_score   REAL DEFAULT 0,
    status          TEXT DEFAULT 'active',      -- active | left | flagged
    UNIQUE(exam_id, tracker_id)
);

-- ---------------------------------------------------------------------
-- Incidents (suspicious activity events)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id         INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    track_id        INTEGER NOT NULL REFERENCES student_tracks(id) ON DELETE CASCADE,
    incident_type   TEXT NOT NULL,   -- looking_away | mobile_phone | standing | left_seat |
                                      -- object_passing | face_not_visible | close_interaction
    confidence      REAL DEFAULT 0,
    score_delta     REAL DEFAULT 0,
    screenshot_path TEXT,
    description     TEXT,
    review_status   TEXT DEFAULT 'pending',   -- pending | confirmed | false_alarm (giám thị xác nhận)
    reviewed_at     TEXT,
    timestamp       TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- Reports (generated PDF exports)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id         INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    generated_by    INTEGER REFERENCES admin_users(id),
    generated_at    TEXT DEFAULT (datetime('now')),
    summary         TEXT
);

-- ---------------------------------------------------------------------
-- System settings (key/value store for configurable runtime options)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_incidents_exam ON incidents(exam_id);
CREATE INDEX IF NOT EXISTS idx_incidents_track ON incidents(track_id);
CREATE INDEX IF NOT EXISTS idx_tracks_exam ON student_tracks(exam_id);
CREATE INDEX IF NOT EXISTS idx_incidents_time ON incidents(timestamp);
