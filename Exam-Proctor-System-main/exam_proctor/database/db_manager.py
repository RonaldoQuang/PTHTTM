"""
database/db_manager.py
-----------------------
Thin, reusable wrapper around SQLite so no other module writes raw
SQL connection boilerplate. Uses a single-writer pattern safe for
Flask's threaded dev server (SQLite connections are per-call).
"""

import sqlite3
import os
from contextlib import contextmanager

from config.config import Config


class DatabaseManager:
    """Handles all SQLite access for the application."""

    def __init__(self, db_path: str = None, schema_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        self.schema_path = schema_path or Config.SCHEMA_PATH
        Config.ensure_directories()
        self._initialize_schema()

    @contextmanager
    def get_connection(self):
        """Yield a connection with row access by column name."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_schema(self):
        """Create tables on first run if the DB file doesn't exist yet."""
        first_run = not os.path.exists(self.db_path)
        with self.get_connection() as conn:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        if first_run:
            self._seed_defaults()

    def _seed_defaults(self):
        """Seed a default admin account and settings on first run."""
        from auth.auth_manager import AuthManager  # local import avoids circular import

        auth = AuthManager(self)
        if not auth.get_user_by_username("admin"):
            auth.create_user("admin", "admin123", full_name="Administrator", role="admin")

        defaults = {
            "suspicion_threshold": str(Config.SUSPICION_ALERT_THRESHOLD),
            "camera_source": str(Config.CAMERA_SOURCE),
        }
        with self.get_connection() as conn:
            for k, v in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v)
                )

    # ------------------------------------------------------------ generic
    def execute(self, query: str, params: tuple = ()):
        """Run an INSERT/UPDATE/DELETE, returns lastrowid."""
        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            return cur.lastrowid

    def fetch_one(self, query: str, params: tuple = ()):
        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: tuple = ()):
        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
