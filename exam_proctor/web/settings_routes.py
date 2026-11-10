"""
web/settings_routes.py
-------------------------
System settings page: adjust the suspicion alert threshold and default
camera source (stored in system_settings), and change the admin
password.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session

from web.auth_routes import login_required

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings", methods=["GET", "POST"])
@login_required
def index():
    db = current_app.config["DB"]

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "general":
            threshold = request.form.get("suspicion_threshold", "15")
            camera_source = request.form.get("camera_source", "0")
            db.execute(
                "INSERT INTO system_settings (key, value) VALUES ('suspicion_threshold', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (threshold,),
            )
            db.execute(
                "INSERT INTO system_settings (key, value) VALUES ('camera_source', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (camera_source,),
            )
            flash("Đã cập nhật cài đặt.", "success")

        elif form_type == "password":
            new_password = request.form.get("new_password", "")
            auth_manager = current_app.config["AUTH_MANAGER"]
            if len(new_password) < 6:
                flash("Mật khẩu phải có ít nhất 6 ký tự.", "danger")
            else:
                auth_manager.change_password(session["user_id"], new_password)
                flash("Đổi mật khẩu thành công.", "success")

        return redirect(url_for("settings.index"))

    settings_rows = db.fetch_all("SELECT * FROM system_settings")
    settings_map = {r["key"]: r["value"] for r in settings_rows}
    return render_template("settings.html", settings=settings_map)
