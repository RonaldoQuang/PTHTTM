"""
web/report_routes.py
-----------------------
Lists exams and generated reports, and triggers new PDF report
generation via reports.report_generator.ReportGenerator.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, current_app, session, send_from_directory

from web.auth_routes import login_required
from reports.report_generator import ReportGenerator
from config.config import Config

report_bp = Blueprint("report", __name__)


@report_bp.route("/reports")
@login_required
def index():
    db = current_app.config["DB"]
    exams = db.fetch_all("SELECT * FROM exams ORDER BY created_at DESC")
    reports = db.fetch_all(
        """SELECT reports.*, exams.exam_name FROM reports
           JOIN exams ON reports.exam_id = exams.id
           ORDER BY reports.generated_at DESC"""
    )
    return render_template("reports.html", exams=exams, reports=reports)


@report_bp.route("/reports/generate/<int:exam_id>", methods=["POST"])
@login_required
def generate(exam_id):
    db = current_app.config["DB"]
    generator = ReportGenerator(db)
    try:
        generator.generate(exam_id, generated_by=session.get("user_id"))
        flash("Report generated successfully.", "success")
    except Exception as exc:
        flash(f"Failed to generate report: {exc}", "danger")
    return redirect(url_for("report.index"))


@report_bp.route("/reports/download/<path:filename>")
@login_required
def download(filename):
    return send_from_directory(Config.REPORT_DIR, filename, as_attachment=True)
