"""
analysis/pose_rules.py
----------------------
Các LUẬT (heuristic) suy ra hành vi đáng ngờ từ 17 keypoint của YOLO-pose.
Chỉ là hàm thuần (không đọc camera, không ghi DB) nên dễ test và dễ chỉnh ngưỡng.

Chỉ số keypoint COCO: 0 mũi, 1-2 mắt, 3-4 tai, 5-6 vai, 9-10 cổ tay, 11-12 hông.
Mỗi keypoint là (x, y, độ tin cậy).
"""
import numpy as np

# Thứ tự ưu tiên khi một người có nhiều cảnh báo cùng lúc: chỉ giữ cảnh báo quan trọng nhất
PRIORITY_ORDER = ["DUNG DAY", "NAM RA BAN", "GIO TAY CAO", "QUAY DAU", "CUI GAM MAT", "CUI DAU THAP"]

# --- Các ngưỡng (chỉnh tại đây khi hiệu chỉnh theo góc camera) ---
KPT_CONF = 0.2                 # keypoint được coi là "thấy rõ"
KPT_CONF_MISSING = 0.12        # dưới mức này coi là "không thấy"
HEAD_TURN_RATIO = 2.5          # tỉ lệ khoảng cách mũi-mắt trái/phải để coi là quay đầu
BOW_ANGLE_DEG = 115            # góc mũi-vai-hông nhỏ hơn mức này = cúi đầu thấp
LYING_TORSO_RATIO = 0.55       # khoảng cách vai-hông / bề rộng vai nhỏ hơn mức này (và mất mặt) = nằm ra bàn
STANDING_ASPECT = 1.65         # cao/rộng của khung người phải lớn hơn mức này
STANDING_ASPECT_STRONG = 2.2   # khung RẤT cao thì đủ để kết luận đứng dậy
LOWER_BODY_CONF = 0.3          # đầu gối/mắt cá chân (keypoint 13-16) coi là thấy rõ
LOWER_BODY_MIN_VISIBLE = 2     # số điểm thân dưới phải thấy: người ngồi sau bàn thường bị che
STANDING_MIN_HEIGHT = 60       # px, bỏ qua khung quá nhỏ


def calculate_angle(A, B, C):
    """Góc (độ) tại đỉnh B của A-B-C. Trả về None nếu keypoint không đủ tin cậy."""
    if A[2] < 0.15 or B[2] < 0.15 or C[2] < 0.15:
        return None
    ba = np.array([A[0] - B[0], A[1] - B[1]])
    bc = np.array([C[0] - B[0], C[1] - B[1]])
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    if norm_ba == 0 or norm_bc == 0:
        return None
    cosine_angle = np.clip(np.dot(ba, bc) / (norm_ba * norm_bc), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine_angle)))


def analyze_pose_warnings(person_kpts, box=None):
    """Trả về danh sách mã cảnh báo (QUAY DAU, CUI GAM MAT, CUI DAU THAP, GIO TAY CAO, NAM RA BAN, DUNG DAY)."""
    nose = person_kpts[0]
    l_eye, r_eye = person_kpts[1], person_kpts[2]
    l_ear, r_ear = person_kpts[3], person_kpts[4]
    l_shoulder, r_shoulder = person_kpts[5], person_kpts[6]
    l_hip, r_hip = person_kpts[11], person_kpts[12]
    l_wrist, r_wrist = person_kpts[9], person_kpts[10]

    warnings = []

    shoulder_width = 0
    if l_shoulder[2] > KPT_CONF and r_shoulder[2] > KPT_CONF:
        shoulder_width = abs(l_shoulder[0] - r_shoulder[0])

    mid_shoulder = [(l_shoulder[0] + r_shoulder[0]) / 2.0, (l_shoulder[1] + r_shoulder[1]) / 2.0,
                    min(l_shoulder[2], r_shoulder[2])]
    mid_hip = [(l_hip[0] + r_hip[0]) / 2.0, (l_hip[1] + r_hip[1]) / 2.0, min(l_hip[2], r_hip[2])]

    # QUAY ĐẦU
    is_turning_head = False
    if nose[2] > KPT_CONF and l_eye[2] > KPT_CONF and r_eye[2] > KPT_CONF:
        dist_l = abs(nose[0] - l_eye[0])
        dist_r = abs(nose[0] - r_eye[0])
        if dist_r > 0 and (dist_l / dist_r > HEAD_TURN_RATIO or dist_r / dist_l > HEAD_TURN_RATIO):
            is_turning_head = True
    elif (l_eye[2] > KPT_CONF and r_eye[2] < KPT_CONF_MISSING) or (r_eye[2] > KPT_CONF and l_eye[2] < KPT_CONF_MISSING):
        is_turning_head = True
    elif (l_ear[2] > KPT_CONF and r_ear[2] < 0.1) or (r_ear[2] > KPT_CONF and l_ear[2] < 0.1):
        is_turning_head = True
    if is_turning_head:
        warnings.append("QUAY DAU")

    # CÚI GẦM MẶT & CÚI ĐẦU THẤP
    face_lost = nose[2] < KPT_CONF_MISSING and l_eye[2] < KPT_CONF_MISSING and r_eye[2] < KPT_CONF_MISSING
    shoulders_visible = l_shoulder[2] > KPT_CONF or r_shoulder[2] > KPT_CONF
    if face_lost and shoulders_visible:
        warnings.append("CUI GAM MAT")

    angle_head_body = calculate_angle(nose, mid_shoulder, mid_hip)
    if angle_head_body is not None and angle_head_body < BOW_ANGLE_DEG:
        warnings.append("CUI DAU THAP")

    # GIƠ TAY CAO (cổ tay cao hơn mắt)
    if (l_wrist[2] > 0.25 and l_eye[2] > KPT_CONF and l_wrist[1] < l_eye[1]) or \
       (r_wrist[2] > 0.25 and r_eye[2] > KPT_CONF and r_wrist[1] < r_eye[1]):
        warnings.append("GIO TAY CAO")

    # NẰM RA BÀN
    if shoulders_visible and mid_shoulder[2] > KPT_CONF and mid_hip[2] > KPT_CONF and shoulder_width > 5:
        if abs(mid_shoulder[1] - mid_hip[1]) < LYING_TORSO_RATIO * shoulder_width and face_lost:
            warnings.append("NAM RA BAN")

    # ĐỨNG DẬY (dựa vào tỉ lệ khung người)
    if box is not None:
        box_height = box[3] - box[1]
        box_width = box[2] - box[0]
        if box_width > 0 and box_height > STANDING_MIN_HEIGHT:
            aspect = box_height / box_width
            lower_visible = sum(1 for i in (13, 14, 15, 16) if person_kpts[i][2] > LOWER_BODY_CONF)
            # Người ngồi cúi/nghiêng người cũng có khung cao, nên cần thêm bằng chứng: thấy chân, hoặc khung rất cao
            if aspect > STANDING_ASPECT_STRONG or (aspect > STANDING_ASPECT and lower_visible >= LOWER_BODY_MIN_VISIBLE):
                warnings.append("DUNG DAY")

    return warnings


def pick_main_warning(warnings):
    """Chọn 1 cảnh báo quan trọng nhất theo PRIORITY_ORDER (None nếu không có)."""
    for p in PRIORITY_ORDER:
        for w in warnings:
            if p in w:
                return w
    return warnings[0] if warnings else None
