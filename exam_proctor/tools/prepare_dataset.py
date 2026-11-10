"""
tools/prepare_dataset.py
------------------------
Chuẩn bị dữ liệu để FINE-TUNE model vật thể bằng chính video phòng thi của bạn.

  python tools/prepare_dataset.py video1.mp4 video2.mp4 --every 2
  (hoặc truyền cả thư mục chứa video)

Việc script làm:
  1. Lấy 1 frame mỗi N giây (bỏ frame gần giống frame trước).
  2. Gán nhãn NHÁP bằng 3 model hiện tại -> 2 lớp: 0 phone, 1 cheat_paper (định dạng YOLO .txt).
  3. Đóng gói thành dataset_for_roboflow.zip (images/ + labels/ + data.yaml).

Sau đó: upload zip lên Roboflow (Create New Project -> Object Detection -> Upload -> kéo cả file zip),
SỬA nhãn (xóa box sai, vẽ thêm box bị thiếu), Generate -> Export "YOLOv11" -> train bằng tools/train_objects.py.
Nhãn nháp chỉ để đỡ phải vẽ từ đầu; model hiện tại hay sai nên BẮT BUỘC kiểm tra lại từng ảnh.
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CLASSES = ["phone", "cheat_paper"]
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def kind_to_id(name):
    n = name.lower()
    if "phone" in n:
        return 0
    if "paper" in n or "cheat" in n or "document" in n:
        return 1
    return None   # laptop và các lớp khác bị bỏ qua


def iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def prelabel(models, frame, conf):
    """Chạy các model, gộp kết quả (bỏ box trùng cùng lớp, giữ box conf cao nhất). Trả về [(cls, conf, xyxy)]."""
    dets = []
    for model, classes in models:
        res = model(frame, conf=conf, classes=classes, imgsz=640, verbose=False)[0]
        for box in res.boxes:
            cid = kind_to_id(res.names[int(box.cls[0])])
            if cid is not None:
                dets.append((cid, float(box.conf[0]), [float(v) for v in box.xyxy[0]]))
    dets.sort(key=lambda d: -d[1])
    kept = []
    for d in dets:
        if all(not (k[0] == d[0] and iou(k[2], d[2]) > 0.5) for k in kept):
            kept.append(d)
    return kept


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", help="file video hoặc thư mục chứa video")
    ap.add_argument("--every", type=float, default=2.0, help="lấy 1 frame mỗi N giây (mặc định 2)")
    ap.add_argument("--conf", type=float, default=0.25, help="ngưỡng gán nhãn nháp (thấp để ít bị sót, mặc định 0.25)")
    ap.add_argument("--diff", type=float, default=6.0, help="bỏ frame giống frame trước (độ lệch ảnh trung bình < giá trị này)")
    ap.add_argument("--out", default="dataset_raw")
    ap.add_argument("--no-prelabel", action="store_true", help="chỉ lấy frame, không gán nhãn nháp")
    args = ap.parse_args()

    files = []
    for p in map(Path, args.videos):
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT) if p.is_dir() else [p]
    if not files:
        sys.exit("Không tìm thấy video nào.")

    models = []
    if not args.no_prelabel:
        from detection.model_loader import load_yolo
        models = [(load_yolo("train_myself-cheat_paper.pt", "detect"), None),
                  (load_yolo("train_myself-phone_and_laptop2.pt", "detect"), None)]
        phone = load_yolo("phone_detection.pt", "detect")
        models.append((phone, [k for k, v in phone.names.items() if v == "phone"]))

    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "images").mkdir(parents=True)
    (out / "labels").mkdir()
    saved = boxes = 0
    for vi, vf in enumerate(files, 1):
        cap = cv2.VideoCapture(str(vf))
        if not cap.isOpened():
            print(f"Bỏ qua (không mở được): {vf}")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(args.every * fps)))
        idx, last_small, n_vid = -1, None, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if idx % step:
                continue
            small = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            if last_small is not None and float(np.abs(small - last_small).mean()) < args.diff:
                continue
            last_small = small
            name = f"v{vi:02d}_{idx:06d}"
            cv2.imwrite(str(out / "images" / f"{name}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            lines = []
            if models:
                h, w = frame.shape[:2]
                for cid, c, (x1, y1, x2, y2) in prelabel(models, frame, args.conf):
                    lines.append(f"{cid} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
            (out / "labels" / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
            saved += 1; n_vid += 1; boxes += len(lines)
        cap.release()
        print(f"{vf.name}: {n_vid} frame")
    (out / "data.yaml").write_text(
        "path: .\ntrain: images\nval: images\nnames:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASSES)),
        encoding="utf-8")

    zpath = out.with_name("dataset_for_roboflow.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    print(f"\nXong: {saved} ảnh, {boxes} box nháp -> {zpath}")
    print("Bước tiếp: upload zip lên Roboflow, SỬA nhãn, export YOLOv11, rồi chạy tools/train_objects.py")
    if saved < 150:
        print(f"Lưu ý: mới có {saved} ảnh. Nên có ít nhất 200-300 ảnh (thêm video / giảm --every) để fine-tune có ý nghĩa.")


if __name__ == "__main__":
    main()
