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
from utils.helpers import find_unicode_font, fold_vietnamese, incident_label, status_label, vn_datetime


class ExamReportPDF(FPDF):
    """PDF hỗ trợ tiếng Việt: dùng font Unicode có sẵn trên máy (Arial/Segoe/DejaVu...).
    Nếu không tìm thấy font, tự bỏ dấu để vẫn tạo được báo cáo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unicode_ok = False
        self.font_name = "Helvetica"
        fonts = find_unicode_font()
        if fonts:
            try:
                self.add_font("VN", "", fonts["regular"])
                self.add_font("VN", "B", fonts["bold"])
                self.add_font("VN", "I", fonts["italic"])
                self.font_name = "VN"
                self.unicode_ok = True
            except Exception as exc:
                print(f"[ReportGenerator] Không nạp được font Unicode, sẽ bỏ dấu tiếng Việt: {exc}")

    def cell(self, w=None, h=None, txt="", *args, **kwargs):
        txt = "" if txt is None else str(txt)
        if not self.unicode_ok:
            txt = fold_vietnamese(txt)
        return super().cell(w, h, txt, *args, **kwargs)

    def header(self):
        self.set_font(self.font_name, "B", 14)
        self.cell(0, 10, Config.REPORT_LOGO_TEXT, ln=True, align="C")
        self.set_font(self.font_name, "", 9)
        self.cell(0, 6, "Tóm tắt hoạt động đáng ngờ (không phải kết luận cuối cùng về gian lận)", ln=True, align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_name, "I", 8)
        self.cell(0, 10, f"Trang {self.page_no()}", align="C")


class ReportGenerator:
    """Generates and saves PDF reports for a completed/ongoing exam."""

    def __init__(self, db_manager):
        self.db = db_manager

    def generate(self, exam_id: int, generated_by: int = None) -> str:
        exam = self.db.fetch_one("SELECT * FROM exams WHERE id = ?", (exam_id,))
        if not exam:
            raise ValueError(f"Không tìm thấy kỳ thi {exam_id}")

        incidents = self.db.fetch_all(
            """SELECT incidents.*, student_tracks.tracker_id, student_tracks.display_label
               FROM incidents
               JOIN student_tracks ON incidents.track_id = student_tracks.id
               WHERE incidents.exam_id = ? AND COALESCE(incidents.review_status, 'pending') != 'false_alarm'
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

        relative_path = f"reports/{filename}"
        self.db.execute(
            """INSERT INTO reports (exam_id, file_path, generated_by, summary)
               VALUES (?, ?, ?, ?)""",
            (exam_id, relative_path, generated_by, f"{len(incidents)} sự cố (đã loại các sự cố giám thị đánh dấu báo nhầm) trên {len(tracks)} chỗ ngồi"),
        )
        return relative_path

    # ------------------------------------------------------------- pieces
    def _add_exam_info(self, pdf: FPDF, exam: dict):
        pdf.set_font(pdf.font_name, "B", 12)
        pdf.cell(0, 8, "Thông tin kỳ thi", ln=True)
        pdf.set_font(pdf.font_name, "", 10)
        rows = [
            ("Tên kỳ thi", exam.get("exam_name")),
            ("Môn học", exam.get("subject")),
            ("Phòng thi", exam.get("room_name")),
            ("Ngày thi", vn_datetime(exam.get("exam_date"))),
            ("Thời gian", f"{exam.get('start_time') or ''} - {exam.get('end_time') or ''}"),
            ("Trạng thái", status_label(exam.get("status"))),
        ]
        for label, value in rows:
            pdf.cell(40, 6, f"{label}:", border=0)
            pdf.cell(0, 6, str(value or "-"), ln=True)
        pdf.ln(4)

    def _add_track_summary(self, pdf: FPDF, tracks: list):
        pdf.set_font(pdf.font_name, "B", 12)
        pdf.cell(0, 8, "Tổng hợp theo thí sinh", ln=True)
        pdf.set_font(pdf.font_name, "B", 9)
        pdf.cell(30, 7, "Mã theo dõi", border=1)
        pdf.cell(60, 7, "Nhãn", border=1)
        pdf.cell(40, 7, "Điểm cuối", border=1)
        pdf.cell(40, 7, "Trạng thái", border=1, ln=True)
        pdf.set_font(pdf.font_name, "", 9)
        for t in tracks:
            pdf.cell(30, 7, str(t["tracker_id"]), border=1)
            pdf.cell(60, 7, str(t["display_label"] or ""), border=1)
            pdf.cell(40, 7, f"{t['current_score']:.1f}", border=1)
            pdf.cell(40, 7, status_label(t["status"]), border=1, ln=True)
        pdf.ln(4)

    def _add_incident_table(self, pdf: FPDF, incidents: list):
        pdf.set_font(pdf.font_name, "B", 12)
        pdf.cell(0, 8, "Nhật ký sự cố", ln=True)
        pdf.set_font(pdf.font_name, "B", 8)
        pdf.cell(15, 7, "Mã", border=1)
        pdf.cell(40, 7, "Loại", border=1)
        pdf.cell(38, 7, "Thời gian", border=1)
        pdf.cell(22, 7, "Tin cậy", border=1)
        pdf.cell(75, 7, "Mô tả", border=1, ln=True)
        pdf.set_font(pdf.font_name, "", 8)
        for inc in incidents:
            pdf.cell(15, 6, str(inc["tracker_id"]), border=1)
            pdf.cell(40, 6, incident_label(inc["incident_type"]), border=1)
            pdf.cell(38, 6, vn_datetime(inc["timestamp"]), border=1)
            pdf.cell(22, 6, f"{(inc['confidence'] or 0) * 100:.0f}%", border=1)
            desc = (inc["description"] or "")[:50]
            pdf.cell(75, 6, desc, border=1, ln=True)
        pdf.ln(4)

    def _add_evidence_pages(self, pdf: FPDF, incidents: list):
        evidence = [i for i in incidents if i.get("screenshot_path")]
        if not evidence:
            return
        pdf.add_page()
        pdf.set_font(pdf.font_name, "B", 12)
        pdf.cell(0, 8, "Ảnh bằng chứng", ln=True)
        pdf.set_font(pdf.font_name, "", 9)

        static_dir = os.path.join(Config.BASE_DIR if hasattr(Config, "BASE_DIR") else "", "static") \
            if hasattr(Config, "BASE_DIR") else None

        from config.config import BASE_DIR
        for inc in evidence:
            img_path = os.path.join(BASE_DIR, "static", inc["screenshot_path"])
            if not os.path.exists(img_path):
                continue
            pdf.cell(0, 6, f"Mã {inc['tracker_id']} - {incident_label(inc['incident_type'])} - {vn_datetime(inc['timestamp'])}", ln=True)
            try:
                pdf.image(img_path, h=60)
            except Exception:
                pdf.cell(0, 6, "[không chèn được ảnh]", ln=True)
            pdf.ln(4)
