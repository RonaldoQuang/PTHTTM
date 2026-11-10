"""
export_openvino.py
------------------
Xuất 4 model sang OpenVINO để chạy nhanh hơn trên CPU/GPU Intel (không cần train lại).
Chạy 1 lần:   python export_openvino.py
Sau đó chạy app bình thường: MonitoringService tự dùng thư mục models/<tên>_openvino_model.
Muốn quay về PyTorch: xóa các thư mục *_openvino_model trong models/.

Kích thước xuất lấy từ config/config.py (POSE_IMGSZ, OBJECT_IMGSZ). Đổi các giá trị đó thì phải chạy lại file này.
Nếu quên, hệ thống tự phát hiện bản OpenVINO cũ không khớp và dùng tạm file .pt.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ultralytics import YOLO

from config.config import Config
MODEL_DIR = Path(__file__).resolve().parent / "models"
# (file model, kích thước xuất): pose theo Config.POSE_IMGSZ, các model vật thể theo Config.OBJECT_IMGSZ
FILES = [("yolo11n-pose.pt", Config.POSE_IMGSZ),
         ("train_myself-cheat_paper.pt", Config.OBJECT_IMGSZ),
         ("train_myself-phone_and_laptop2.pt", Config.OBJECT_IMGSZ),
         (Config.OBJECT_MODEL_FILE, Config.OBJECT_IMGSZ)]
if Config.USE_INCAR_PHONE_MODEL:
    FILES.append(("phone_detection.pt", Config.OBJECT_IMGSZ))

for name, imgsz in FILES:
    path = MODEL_DIR / name
    if not path.exists():
        print(f"Bỏ qua (không thấy file): {path}")
        continue
    print(f"== Đang xuất {name} (imgsz={imgsz}) ...")
    out = Path(YOLO(str(path)).export(format="openvino", imgsz=imgsz, half=False, dynamic=False))
    target = MODEL_DIR / f"{path.stem}_openvino_model"
    if out.resolve() != target.resolve():
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(out), str(target))
    print("   ->", target)
print("Xong.")
