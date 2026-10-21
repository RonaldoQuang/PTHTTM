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


def create_app(env: str = None):
    env = env or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_MAP.get(env, CONFIG_MAP["development"]))

    Config.ensure_directories()

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
        from flask import session
        return {"current_username": session.get("username"), "current_role": session.get("role")}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
