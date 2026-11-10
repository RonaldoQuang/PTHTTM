
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
from config.config import Config

monitor_bp = Blueprint("monitor", __name__)


def frame_to_jpeg_bytes(frame):
    """Mã hóa frame numpy array sang định dạng JPEG bytes với kích thước và chất lượng tối ưu tốc độ truyền tải."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if w > 960:
        frame = cv2.resize(frame, (960, int(h * 960 / w)))
    success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not success:
        return None
    return buffer.tobytes()


@monitor_bp.route("/live", methods=["GET"])
@login_required
def live():
    db = current_app.config["DB"]
    exams = db.fetch_all("SELECT * FROM exams ORDER BY created_at DESC LIMIT 20")
    monitor = current_app.config.get("ACTIVE_MONITOR")
    running = bool(monitor and monitor.is_running)
    return render_template("live_monitor.html", exams=exams, is_running=running,
                           active_exam_id=monitor.exam_id if running else None)


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
    flash("Đã tạo kỳ thi. Bạn có thể bắt đầu giám sát.", "success")
    return redirect(url_for("monitor.live", exam_id=exam_id))


@monitor_bp.route("/live/start/<int:exam_id>", methods=["POST"])
@login_required
def start_monitoring(exam_id):
    db = current_app.config["DB"]

    existing = current_app.config.get("ACTIVE_MONITOR")
    if existing and existing.is_running:
        flash("Đang giám sát một kỳ thi khác. Hãy dừng phiên đó trước.", "warning")
        return redirect(url_for("monitor.live"))

    # Làm mới lại toàn bộ danh sách cảnh báo và dữ liệu thí sinh của kỳ thi khi bắt đầu giám sát
    try:
        if os.path.isdir(Config.SCREENSHOT_DIR):
            for f in os.listdir(Config.SCREENSHOT_DIR):
                if f.startswith(f"exam{exam_id}_"):
                    try:
                        os.remove(os.path.join(Config.SCREENSHOT_DIR, f))
                    except OSError:
                        pass
        db.execute("DELETE FROM incidents WHERE exam_id = ?", (exam_id,))
        db.execute("DELETE FROM student_tracks WHERE exam_id = ?", (exam_id,))
    except Exception as exc:
        print(f"[start_monitoring] Lỗi khi làm mới cảnh báo cũ: {exc}")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    camera_source = None

    # 1. Kiểm tra xem người dùng có chọn upload file video từ máy tính không
    video_file = request.files.get("video_file")
    if video_file and video_file.filename and video_file.filename.strip():
        from werkzeug.utils import secure_filename
        filename = secure_filename(video_file.filename)
        if os.path.splitext(filename)[1].lower() not in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            flash("Chỉ chấp nhận video .mp4/.avi/.mov/.mkv/.webm.", "danger")
            return redirect(url_for("monitor.live"))
        if not filename:
            filename = f"video_{int(time.time())}.mp4"
        else:
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"

        upload_dir = os.path.join(base_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        saved_path = os.path.join(upload_dir, filename)
        video_file.save(saved_path)
        camera_source = saved_path
    else:
        # 2. Nếu không có file tải lên, kiểm tra ô nhập (nếu có nhập thủ công)
        raw_source = request.form.get("camera_source", "")
        if raw_source:
            raw_source = raw_source.strip().strip("'\"")
            if raw_source.isdigit():
                camera_source = int(raw_source)
            else:
                if not os.path.isabs(raw_source) and not raw_source.startswith(("rtsp://", "http://", "https://")):
                    camera_source = os.path.join(base_dir, raw_source)
                else:
                    camera_source = raw_source
        else:
            # 3. Mặc định là nguồn 0 (webcam)
            camera_source = 0

    try:
        monitor = MonitoringService(db, exam_id, camera_source=camera_source)
    except Exception as exc:
        flash(f"Không khởi tạo được giám sát: {exc}", "danger")
        return redirect(url_for("monitor.live"))
    if not monitor.start():
        flash("Không mở được nguồn camera/video. Hãy kiểm tra file video hoặc camera có sẵn sàng không.", "danger")
        return redirect(url_for("monitor.live"))

    current_app.config["ACTIVE_MONITOR"] = monitor
    db.execute("UPDATE exams SET status = 'running' WHERE id = ?", (exam_id,))
    flash("Đã bắt đầu giám sát.", "success")
    return redirect(url_for("monitor.live"))


@monitor_bp.route("/live/stop", methods=["POST"])
@login_required
def stop_monitoring():
    monitor = current_app.config.get("ACTIVE_MONITOR")
    if monitor:
        monitor.stop()
        current_app.config["DB"].execute("UPDATE exams SET status = 'completed' WHERE id = ?", (monitor.exam_id,))
        current_app.config["ACTIVE_MONITOR"] = None
        flash("Đã dừng giám sát.", "info")
    return redirect(url_for("monitor.live"))


@monitor_bp.route("/live/clear-incidents/<int:exam_id>", methods=["POST"])
@login_required
def clear_incidents(exam_id):
    """Xóa làm mới danh sách cảnh báo và dữ liệu thí sinh của kỳ thi."""
    db = current_app.config["DB"]
    try:
        if os.path.isdir(Config.SCREENSHOT_DIR):
            for f in os.listdir(Config.SCREENSHOT_DIR):
                if f.startswith(f"exam{exam_id}_"):
                    try:
                        os.remove(os.path.join(Config.SCREENSHOT_DIR, f))
                    except OSError:
                        pass
        db.execute("DELETE FROM incidents WHERE exam_id = ?", (exam_id,))
        db.execute("DELETE FROM student_tracks WHERE exam_id = ?", (exam_id,))

        monitor = current_app.config.get("ACTIVE_MONITOR")
        if monitor and monitor.is_running and monitor.exam_id == exam_id:
            if hasattr(monitor, "recorder") and monitor.recorder:
                monitor.recorder.reset()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@monitor_bp.route("/live/feed")
@monitor_bp.route("/video_feed")
@login_required
def video_feed():
    """MJPEG streaming route hỗ trợ cả /live/feed và /video_feed."""
    app = current_app._get_current_object()

    def generate():
        with app.app_context():
            try:
                while True:
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
                        jpeg_bytes = frame_to_jpeg_bytes(frame) if frame is not None else None

                    if not jpeg_bytes:
                        time.sleep(0.03)
                        continue

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n"
                    )
                    time.sleep(0.03)  # Giới hạn ~30 FPS
            except (GeneratorExit, ConnectionResetError, BrokenPipeError):
                pass
            except Exception as e:
                print(f"[video_feed] Stream ended: {e}")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@monitor_bp.route("/live/status")
@login_required
def status():
    monitor = current_app.config.get("ACTIVE_MONITOR")
    return jsonify({"running": bool(monitor and monitor.is_running)})
