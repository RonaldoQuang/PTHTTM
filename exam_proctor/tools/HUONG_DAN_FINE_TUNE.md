# Fine-tune model vật thể (điện thoại / phao thi)

Mục tiêu: thay 3 model rời (train trên dữ liệu khác miền) bằng **1 model 2 lớp** học từ chính video phòng thi của bạn.

## Bước 1. Chuẩn bị dữ liệu (máy của bạn)
```
python tools/prepare_dataset.py video1.mp4 video2.mp4 --every 2
```
- Tạo `dataset_for_roboflow.zip` (ảnh + nhãn nháp). Cần **200-300 ảnh trở lên**: thêm video, hoặc giảm `--every 1`.
- Video nên đa dạng: nhiều góc, nhiều người, có đủ cả điện thoại, phao thi **và cả cảnh bình thường** (để model học không báo nhầm).

## Bước 2. Sửa nhãn trên Roboflow (quan trọng nhất)
1. Tạo project *Object Detection*, upload file zip.
2. Với từng ảnh: **xóa box sai**, **vẽ thêm box bị sót**. Tên lớp đúng: `phone`, `cheat_paper`.
3. Ảnh không có vật nào thì để trống (không nhãn): đây là ví dụ "âm" giúp giảm báo nhầm.
4. *Generate* version -> *Export* -> định dạng **YOLOv11** -> tải zip về (hoặc lấy link/code để dùng trên Colab).
5. Có thể thêm ảnh từ các bộ công khai trên Roboflow Universe (kiểm tra giấy phép), nhớ đổi tên lớp cho khớp.

## Bước 3. Train (Colab GPU T4 miễn phí)
```
pip install ultralytics
python tools/train_objects.py --data /đường/dẫn/data.yaml --epochs 80
```
Xong sẽ in precision/recall/mAP50 từng lớp. Lấy `runs_objects/v3/weights/best.pt`.

## Bước 4. Dùng trong hệ thống
1. Chép `best.pt` vào `exam_proctor/models/` và **đổi tên thành `train_myself-objects_v3.pt`**.
2. Chạy lại `python export_openvino.py` (nhanh hơn trên CPU Intel).
3. Chạy lại `python evaluate.py` trên video test và so sánh precision với lần trước.
   (Dùng **video khác** với video đã train để số liệu trung thực.)

Hệ thống tự phát hiện file model gộp và bỏ qua 3 model rời cũ. Muốn quay lại model cũ: xóa/đổi tên file `train_myself-objects_v3.pt`.
