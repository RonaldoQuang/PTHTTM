"""
web/dashboard_routes.py
--------------------------
Main dashboard: overview stats, incident history with search/filter,
daily statistics, and chart data feeds consumed by Chart.js.
"""

from flask import Blueprint, render_template, request, jsonify, current_app, url_for, redirect, abort, flash
from utils.helpers import incident_label, incident_severity, vn_datetime

from web.auth_routes import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    db = current_app.config["DB"]

    exams = db.fetch_all("SELECT * FROM exams ORDER BY created_at DESC LIMIT 10")
    total_incidents = db.fetch_one("SELECT COUNT(*) as c FROM incidents")["c"]
    total_tracks = db.fetch_one("SELECT COUNT(*) as c FROM student_tracks")["c"]
    flagged_tracks = db.fetch_one(
        "SELECT COUNT(*) as c FROM student_tracks WHERE status = 'flagged'"
    )["c"]
    recent_incidents = db.fetch_all(
        """SELECT incidents.*, student_tracks.tracker_id, exams.exam_name
           FROM incidents
           JOIN student_tracks ON incidents.track_id = student_tracks.id
           JOIN exams ON incidents.exam_id = exams.id
           ORDER BY incidents.timestamp DESC LIMIT 10"""
    )

    monitor = current_app.config.get("ACTIVE_MONITOR")
    live_stats = monitor.get_live_stats() if (monitor and monitor.is_running and hasattr(monitor, "get_live_stats")) else None

    return render_template(
        "dashboard.html",
        exams=exams,
        total_incidents=total_incidents,
        total_tracks=total_tracks,
        flagged_tracks=flagged_tracks,
        recent_incidents=recent_incidents,
        live_stats=live_stats,
    )


@dashboard_bp.route("/incidents")
@login_required
def incidents():
    db = current_app.config["DB"]

    exam_id = request.args.get("exam_id", type=int)
    incident_type = request.args.get("type", "")
    track_id = request.args.get("track_id", type=int)
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = """SELECT incidents.*, student_tracks.tracker_id, exams.exam_name
               FROM incidents
               JOIN student_tracks ON incidents.track_id = student_tracks.id
               JOIN exams ON incidents.exam_id = exams.id
               WHERE 1=1"""
    params = []

    if exam_id:
        query += " AND incidents.exam_id = ?"
        params.append(exam_id)
    if incident_type:
        query += " AND incidents.incident_type = ?"
        params.append(incident_type)
    if track_id:
        query += " AND student_tracks.tracker_id = ?"
        params.append(track_id)
    if date_from:
        query += " AND date(incidents.timestamp) >= date(?)"
        params.append(date_from)
    if date_to:
        query += " AND date(incidents.timestamp) <= date(?)"
        params.append(date_to)

    query += " ORDER BY incidents.timestamp DESC LIMIT 500"
    results = db.fetch_all(query, tuple(params))
    exams = db.fetch_all("SELECT id, exam_name FROM exams ORDER BY created_at DESC")

    return render_template("incident_details.html", incidents=results, exams=exams,
                            filters=request.args)


@dashboard_bp.route("/incidents/<int:incident_id>/review", methods=["POST"])
@login_required
def review_incident(incident_id):
    """Giám thị xác nhận 1 sự cố: confirmed (đúng) / false_alarm (báo nhầm) / pending (bỏ chọn)."""
    status = request.form.get("status", "")
    if status not in ("pending", "confirmed", "false_alarm"):
        abort(400)
    db = current_app.config["DB"]
    db.execute(
        "UPDATE incidents SET review_status = ?, reviewed_at = CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END WHERE id = ?",
        (status, status, incident_id),
    )
    return redirect(request.referrer or url_for("dashboard.incidents"))


@dashboard_bp.route("/api/chart-data/incident-types")
@login_required
def chart_incident_types():
    db = current_app.config["DB"]
    rows = db.fetch_all(
        "SELECT incident_type, COUNT(*) as count FROM incidents GROUP BY incident_type"
    )
    return jsonify({r["incident_type"]: r["count"] for r in rows})


@dashboard_bp.route("/api/chart-data/daily")
@login_required
def chart_daily():
    db = current_app.config["DB"]
    rows = db.fetch_all(
        """SELECT date(timestamp) as day, COUNT(*) as count
           FROM incidents
           GROUP BY date(timestamp)
           ORDER BY day DESC LIMIT 14"""
    )
    rows.reverse()
    return jsonify({"labels": [r["day"] for r in rows], "counts": [r["count"] for r in rows]})


@dashboard_bp.route("/api/live-stats")
@login_required
def live_stats():
    monitor = current_app.config.get("ACTIVE_MONITOR")
    if monitor and monitor.is_running:
        return jsonify(monitor.get_live_stats())
    return jsonify({"active": False})


@dashboard_bp.route("/api/recent-incidents")
@login_required
def recent_incidents():
    """Danh sách sự cố mới nhất (JSON) để trang Giám sát trực tiếp và Lịch sử sự cố tự cập nhật."""
    db = current_app.config["DB"]
    limit = min(max(request.args.get("limit", 8, type=int), 1), 100)
    exam_id = request.args.get("exam_id", type=int)
    after_id = request.args.get("after_id", type=int)

    query = """SELECT incidents.*, student_tracks.tracker_id, exams.exam_name
               FROM incidents
               JOIN student_tracks ON incidents.track_id = student_tracks.id
               JOIN exams ON incidents.exam_id = exams.id
               WHERE 1=1"""
    params = []
    if exam_id:
        query += " AND incidents.exam_id = ?"
        params.append(exam_id)
    if after_id:
        query += " AND incidents.id > ?"
        params.append(after_id)
        query += " ORDER BY incidents.id ASC LIMIT ?"
    else:
        query += " ORDER BY incidents.id DESC LIMIT ?"
    params.append(limit)

    items = []
    for r in db.fetch_all(query, tuple(params)):
        path = (r["screenshot_path"] or "").replace("\\", "/")
        items.append({
            "id": r["id"],
            "exam": r["exam_name"],
            "track": r["tracker_id"],
            "type": incident_label(r["incident_type"]),
            "raw_type": r["incident_type"],
            "severity": incident_severity(r["incident_type"]),
            "time": vn_datetime(r["timestamp"]),
            "confidence": round((r["confidence"] or 0) * 100),
            "description": r["description"] or "",
            "image": url_for("static", filename=path) if path else "",
            "review_status": r.get("review_status") or "pending",
        })
    resp = jsonify(items)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
