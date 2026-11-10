"""
app.py
-------
Application entry point. Builds the Flask app, wires up the database,
auth manager, and blueprints, then runs the dev server.

Run with:
    python app.py
"""

import os
import sys
from pathlib import Path

# Tự động thêm thư mục chứa app.py vào Python Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ép Working Directory luôn trỏ về đúng thư mục chứa app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
from flask import Flask

from config.config import CONFIG_MAP, Config
from database.db_manager import DatabaseManager
from auth.auth_manager import AuthManager

from web.auth_routes import auth_bp
from web.dashboard_routes import dashboard_bp
from web.monitor_routes import monitor_bp
from web.report_routes import report_bp
from web.settings_routes import settings_bp
from utils.helpers import incident_label, incident_severity, status_label, vn_datetime, INCIDENT_LABELS


def create_app(env: str = None):
    env = env or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_MAP.get(env, CONFIG_MAP["development"]))

    Config.ensure_directories()

    # Bộ lọc dùng trong template để hiển thị tiếng Việt
    app.jinja_env.filters["incident_label"] = incident_label
    app.jinja_env.filters["incident_severity"] = incident_severity
    app.jinja_env.filters["status_label"] = status_label
    app.jinja_env.filters["vn_datetime"] = vn_datetime
    app.jinja_env.globals["INCIDENT_LABELS"] = INCIDENT_LABELS

    db = DatabaseManager()
    auth_manager = AuthManager(db)

    app.config["DB"] = db
    app.config["AUTH_MANAGER"] = auth_manager
    app.config["ACTIVE_MONITOR"] = None  # holds the running MonitoringService, if any

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(settings_bp)

    @app.context_processor
    def inject_globals():
        from flask import session, current_app
        monitor = current_app.config.get("ACTIVE_MONITOR")
        is_monitoring = bool(monitor and monitor.is_running)
        active_exam_name = None
        active_exam_id = None
        if is_monitoring:
            active_exam_id = monitor.exam_id
            db = current_app.config.get("DB")
            if db:
                try:
                    row = db.fetch_one("SELECT exam_name FROM exams WHERE id = ?", (active_exam_id,))
                    if row:
                        active_exam_name = row["exam_name"]
                except Exception:
                    pass
        return {
            "current_username": session.get("username"),
            "current_role": session.get("role"),
            "is_monitoring": is_monitoring,
            "active_exam_id": active_exam_id,
            "active_exam_name": active_exam_name,
        }

    return app


app = create_app()

if __name__ == "__main__":
    # Mặc định chỉ mở trên máy này và tắt debug (debug bật trình gỡ lỗi từ xa + tự khởi động lại làm ngắt giám sát).
    # Muốn thiết bị khác trong mạng truy cập: đặt biến môi trường HOST=0.0.0.0
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        use_reloader=False,
        threaded=True,
    )
