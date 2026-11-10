# Hệ thống giám sát phòng thi bằng AI (đồ án)

Ứng dụng web (Flask) dùng **một camera** để theo dõi thí sinh trong phòng thi, tự động phát hiện
**hành vi đáng ngờ** và **vật cấm**, ghi lại sự cố kèm ảnh bằng chứng để giám thị xem lại.

> **Lưu ý:** hệ thống chỉ *gợi ý hoạt động đáng ngờ* để giám thị kiểm tra, **không kết luận gian lận**.
> Giám thị bấm Đúng / Báo nhầm cho từng sự cố, và báo cáo PDF tự loại các sự cố báo nhầm.

## 1. Chức năng
- Giám sát trực tiếp từ webcam hoặc **video tải lên** (video chạy đúng tốc độ thật).
- Phát hiện hành vi bằng tư thế cơ thể (pose): quay đầu, cúi gằm mặt, cúi đầu thấp, giơ tay cao,
  nằm ra bàn, đứng dậy.
- Phát hiện vật thể: **điện thoại** (phải nằm gần tay thí sinh) và **phao thi (giấy)**.
- **Gán số chỗ ngồi ổn định** theo vị trí (không phụ thuộc ID của bộ theo dõi, vốn hay nhảy).
- Bộ lọc giảm báo nhầm: hành vi phải kéo dài một thời gian mới tính (pose 2 giây, vật thể 1 giây);
  một "đợt" hành vi chỉ ghi một sự cố, lặp lại sau 60 giây mới ghi tiếp.
- **Điểm nghi ngờ** theo từng chỗ ngồi (trọng số mỗi loại sự cố, giảm dần theo thời gian,
  ngưỡng chỉnh ở trang Cài đặt).
- **Popup + âm báo** khi có cảnh báo mới trên trang Giám sát trực tiếp (có nút tắt âm).
- Trang Sự cố: lọc, xem ảnh bằng chứng, **xác nhận Đúng/Báo nhầm**, **xuất CSV**.
- Báo cáo **PDF** (tiếng Việt, kèm ảnh bằng chứng) cho từng kỳ thi.

## 2. Mô hình AI (đều là YOLO11n)
| File trong `models/` | Vai trò |
|---|---|
| `yolo11n-pose.pt` | Tìm người + 17 điểm khớp, kèm theo dõi ByteTrack |
| `train_myself-cheat_paper.pt` | Phát hiện phao thi |
| `train_myself-phone_and_laptop2.pt` | Phát hiện điện thoại (lớp laptop không dùng) |
| `phone_detection.pt` | Model điện thoại phụ, **mặc định tắt** (`USE_INCAR_PHONE_MODEL`) |

Các quy tắc hành vi nằm ở `analysis/pose_rules.py` (code, không phải model) nên **phụ thuộc góc camera**.

## 3. Cấu trúc thư mục
```
app.py                  chạy web
config/config.py        mọi thông số (độ phân giải, ngưỡng, trọng số điểm...)
core/monitoring_service.py   điều phối: đọc khung hình -> model -> lọc -> ghi sự cố
core/incident_recorder.py    ghi sự cố, ảnh bằng chứng, cập nhật điểm
analysis/               pose_rules (luật hành vi), event_filters (lọc), scoring (điểm)
tracking/seat_mapper.py gán số chỗ ngồi
detection/model_loader.py    nạp model, ưu tiên bản OpenVINO
web/ templates/ static/ giao diện web
reports/                tạo PDF
evaluate.py             đánh giá độ chính xác trên video (xem mục 6)
export_openvino.py      xuất model sang OpenVINO để chạy nhanh
tools/                  chuẩn bị dữ liệu + huấn luyện lại model vật thể (tùy chọn)
tests/                  kiểm thử logic (pytest)
```

## 4. Cài đặt và chạy
```
pip install -r requirements.txt
python export_openvino.py     # chỉ 1 lần (và khi đổi POSE_IMGSZ / đổi file model)
python app.py                 # hoặc bấm đúp run_demo.bat
```
Mở http://127.0.0.1:5000 — tài khoản mặc định `admin` / `admin123` (đổi trước khi triển khai thật;
đặt biến môi trường `SECRET_KEY` để cố định khóa phiên).

Cách dùng: **Giám sát trực tiếp** → tạo kỳ thi → chọn kỳ thi, chọn video (bỏ trống = webcam) →
Bắt đầu giám sát. Xong thì vào **Sự cố** để xác nhận và **Báo cáo** để tạo PDF.

## 5. Tốc độ và tầm nhìn
Máy thử: Intel i7-1165G7, 8GB RAM, chạy CPU. PyTorch ~2.5 FPS; sau khi dùng OpenVINO và bỏ bớt
model ~9 FPS ở `POSE_IMGSZ = 960`.
- `POSE_IMGSZ` lớn hơn → thấy được thí sinh ngồi xa hơn nhưng chậm hơn (640 / 960 / 1280).
  Đổi xong phải chạy lại `export_openvino.py`.
- `OBJECT_IMGSZ`, `USE_INCAR_PHONE_MODEL`, `PHONE_HAND_RADIUS`, `ALERT_MIN_CONF` cũng ở `config.py`.

## 6. Đánh giá độ chính xác (tùy chọn)
`python evaluate.py` → chọn 1 (chạy video) → chọn 3 (mở `review.html`, bấm Đúng/Sai) để có bảng
độ chính xác từng loại cảnh báo. Nên quay video đúng góc camera sẽ dùng khi demo.

## 7. Kiểm thử
```
python -m pytest tests
```

## 8. Giới hạn đã biết
- Một camera chỉ theo dõi tốt khoảng 12–20 người; phòng đông hơn cần camera gần hơn hoặc nhiều camera.
- "Quay đầu", "Đứng dậy", "Cúi đầu thấp" phụ thuộc góc camera nên có thể báo nhầm; cần giám thị xác nhận.
- Model vật thể (điện thoại, phao) có thể nhầm hoặc bỏ sót; có thể huấn luyện lại bằng `tools/HUONG_DAN_FINE_TUNE.md`.
- Chưa có nhận diện khuôn mặt (không biết tên thí sinh), chỉ biết số chỗ ngồi.
