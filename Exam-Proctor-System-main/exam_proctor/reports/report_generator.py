"""
reports/report_generator.py
------------------------------
Builds a PDF incident report for a given exam using fpdf2 (pure-Python,
no system dependencies). Includes exam metadata, a summary table of
incidents (track id, type, timestamp, confidence) and embeds evidence
screenshots where available.
"""

import os
import time

from fpdf import FPDF

from config.config import Config


class ExamReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, Config.REPORT_LOGO_TEXT, ln=True, align="C")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, "Suspicious-activity summary (not a definitive cheating determination)", ln=True, align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


class ReportGenerator:
    """Generates and saves PDF reports for a completed/ongoing exam."""

    def __init__(self, db_manager):
        self.db = db_manager

    def generate(self, exam_id: int, generated_by: int = None) -> str:
        exam = self.db.fetch_one("SELECT * FROM exams WHERE id = ?", (exam_id,))
        if not exam:
            raise ValueError(f"Exam {exam_id} not found")

        incidents = self.db.fetch_all(
            """SELECT incidents.*, student_tracks.tracker_id, student_tracks.display_label
               FROM incidents
               JOIN student_tracks ON incidents.track_id = student_tracks.id
               WHERE incidents.exam_id = ?
               ORDER BY incidents.timestamp ASC""",
            (exam_id,),
        )
        tracks = self.db.fetch_all(
            "SELECT * FROM student_tracks WHERE exam_id = ? ORDER BY current_score DESC",
            (exam_id,),
        )

        pdf = ExamReportPDF()
        pdf.add_page()

        self._add_exam_info(pdf, exam)
        self._add_track_summary(pdf, tracks)
        self._add_incident_table(pdf, incidents)
        self._add_evidence_pages(pdf, incidents)

        Config.ensure_directories()
        filename = f"exam_{exam_id}_report_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        abs_path = os.path.join(Config.REPORT_DIR, filename)
        pdf.output(abs_path)

        relative_path = os.path.join("reports", filename)
        self.db.execute(
            """INSERT INTO reports (exam_id, file_path, generated_by, summary)
               VALUES (?, ?, ?, ?)""",
            (exam_id, relative_path, generated_by, f"{len(incidents)} incidents across {len(tracks)} students"),
        )
        return relative_path

    # ------------------------------------------------------------- pieces
    def _add_exam_info(self, pdf: FPDF, exam: dict):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Exam Information", ln=True)
        pdf.set_font("Helvetica", "", 10)
        rows = [
            ("Exam Name", exam.get("exam_name")),
            ("Subject", exam.get("subject")),
            ("Room", exam.get("room_name")),
            ("Date", exam.get("exam_date")),
            ("Time", f"{exam.get('start_time') or ''} - {exam.get('end_time') or ''}"),
            ("Status", exam.get("status")),
        ]
        for label, value in rows:
            pdf.cell(40, 6, f"{label}:", border=0)
            pdf.cell(0, 6, str(value or "-"), ln=True)
        pdf.ln(4)

    def _add_track_summary(self, pdf: FPDF, tracks: list):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Student Track Summary", ln=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(30, 7, "Track ID", border=1)
        pdf.cell(60, 7, "Label", border=1)
        pdf.cell(40, 7, "Final Score", border=1)
        pdf.cell(40, 7, "Status", border=1, ln=True)
        pdf.set_font("Helvetica", "", 9)
        for t in tracks:
            pdf.cell(30, 7, str(t["tracker_id"]), border=1)
            pdf.cell(60, 7, str(t["display_label"] or ""), border=1)
            pdf.cell(40, 7, f"{t['current_score']:.1f}", border=1)
            pdf.cell(40, 7, str(t["status"]), border=1, ln=True)
        pdf.ln(4)

    def _add_incident_table(self, pdf: FPDF, incidents: list):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Incident Log", ln=True)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(15, 7, "Track", border=1)
        pdf.cell(35, 7, "Type", border=1)
        pdf.cell(45, 7, "Timestamp", border=1)
        pdf.cell(25, 7, "Confidence", border=1)
        pdf.cell(70, 7, "Description", border=1, ln=True)
        pdf.set_font("Helvetica", "", 8)
        for inc in incidents:
            pdf.cell(15, 6, str(inc["tracker_id"]), border=1)
            pdf.cell(35, 6, str(inc["incident_type"]), border=1)
            pdf.cell(45, 6, str(inc["timestamp"]), border=1)
            pdf.cell(25, 6, f"{inc['confidence']:.2f}", border=1)
            desc = (inc["description"] or "")[:45]
            pdf.cell(70, 6, desc, border=1, ln=True)
        pdf.ln(4)

    def _add_evidence_pages(self, pdf: FPDF, incidents: list):
        evidence = [i for i in incidents if i.get("screenshot_path")]
        if not evidence:
            return
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Evidence Screenshots", ln=True)
        pdf.set_font("Helvetica", "", 9)

        static_dir = os.path.join(Config.BASE_DIR if hasattr(Config, "BASE_DIR") else "", "static") \
            if hasattr(Config, "BASE_DIR") else None

        from config.config import BASE_DIR
        for inc in evidence:
            img_path = os.path.join(BASE_DIR, "static", inc["screenshot_path"])
            if not os.path.exists(img_path):
                continue
            pdf.cell(0, 6, f"Track {inc['tracker_id']} - {inc['incident_type']} - {inc['timestamp']}", ln=True)
            try:
                pdf.image(img_path, w=100)
            except Exception:
                pdf.cell(0, 6, "[image could not be embedded]", ln=True)
            pdf.ln(4)
