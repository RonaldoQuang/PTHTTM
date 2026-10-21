
"""
web/monitor_routes.py
------------------------
Routes for creating an exam session, starting/stopping monitoring, and
streaming the annotated MJPEG video feed to the live monitoring page.
"""

import time
import os
import cv2
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response, jsonify, session
import sys
from pathlib import Path

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from web.auth_routes import login_required
from core.monitoring_service import MonitoringService

monitor_bp = Blueprint("monitor", __name__)


def frame_to_jpeg_bytes(frame):
    """Mã hóa frame numpy array sang định dạng JPEG bytes."""
    if frame is None:
        return None
    success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not success:
        return None
    return buffer.tobytes()


@monitor_bp.route("/live", methods=["GET"])
@login_required
def live():
    db = current_app.config["DB"]
    exams = db.fetch_all("SELECT * FROM exams ORDER BY created_at DESC LIMIT 20")
    monitor = current_app.config.get("ACTIVE_MONITOR")
    return render_template("live_monitor.html", exams=exams,
                           is_running=bool(monitor and monitor.is_running))


@monitor_bp.route("/live/create-exam", methods=["POST"])
@login_required
def create_exam():
    db = current_app.config["DB"]
    exam_id = db.execute(
        """INSERT INTO exams (exam_name, subject, room_name, exam_date, start_time, end_time, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            request.form.get("exam_name"),
            request.form.get("subject"),
            request.form.get("room_name"),
            request.form.get("exam_date"),
            request.form.get("start_time"),
            request.form.get("end_time"),
            session.get("user_id"),
        ),
    )
    flash("Exam created. You can now start monitoring.", "success")
    return redirect(url_for("monitor.live", exam_id=exam_id))


@monitor_bp.route("/live/start/<int:exam_id>", methods=["POST"])
@login_required
def start_monitoring(exam_id):
    db = current_app.config["DB"]

    existing = current_app.config.get("ACTIVE_MONITOR")
    if existing and existing.is_running():
        flash("Monitoring is already running for another exam. Stop it first.", "warning")
        return redirect(url_for("monitor.live"))

    camera_source = request.form.get("camera_source")
    
    # --- XỬ LÝ VÀ CHUẨN HÓA CAMERA SOURCE ---
    if camera_source:
        camera_source = camera_source.strip().strip("'\"") # Xóa khoảng trắng & dấu nháy dư thừa
        
        if camera_source.isdigit():
            camera_source = int(camera_source)
        else:
            # Nếu là đường dẫn tương đối, chuyển thành đường dẫn tuyệt đối dựa trên thư mục gốc dự án
            if not os.path.isabs(camera_source) and not camera_source.startswith(("rtsp://", "http://", "https://")):
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                camera_source = os.path.join(base_dir, camera_source)

    monitor = MonitoringService(db, exam_id, camera_source=camera_source)
    if not monitor.start():
        flash("Could not open the camera source. Check if the file exists or camera is available.", "danger")
        return redirect(url_for("monitor.live"))

    current_app.config["ACTIVE_MONITOR"] = monitor
    flash("Monitoring started.", "success")
    return redirect(url_for("monitor.live"))


@monitor_bp.route("/live/stop", methods=["POST"])
@login_required
def stop_monitoring():
    monitor = current_app.config.get("ACTIVE_MONITOR")
    if monitor:
        monitor.stop()
        current_app.config["ACTIVE_MONITOR"] = None
        flash("Monitoring stopped.", "info")
    return redirect(url_for("monitor.live"))


@monitor_bp.route("/live/feed")
@monitor_bp.route("/video_feed")
def video_feed():
    """MJPEG streaming route hỗ trợ cả /live/feed và /video_feed."""
    # Lấy app object thực tế trước khi đi vào generator
    app = current_app._get_current_object()

    def generate():
        while True:
            # Sử dụng app_context để tránh RuntimeError: Working outside of application context
            with app.app_context():
                monitor = app.config.get("ACTIVE_MONITOR")
                
                if not monitor or not monitor.is_running:
                    time.sleep(0.1)
                    continue

                # Lấy frame bytes từ monitoring service
                jpeg_bytes = None
                if hasattr(monitor, "get_annotated_frame_bytes"):
                    jpeg_bytes = monitor.get_annotated_frame_bytes()
                elif hasattr(monitor, "get_latest_frame"):
                    frame = monitor.get_latest_frame()
                    jpeg_bytes = frame_to_jpeg_bytes(frame)

                if not jpeg_bytes:
                    time.sleep(0.03)
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
                )
                time.sleep(0.03)  # Giới hạn ~30 FPS

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@monitor_bp.route("/live/status")
@login_required
def status():
    monitor = current_app.config.get("ACTIVE_MONITOR")
    return jsonify({"running": bool(monitor and monitor.is_running())})
