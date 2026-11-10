"""
detection/model_loader.py
-------------------------
Nạp các model YOLO của dự án. Ưu tiên bản OpenVINO (nhanh hơn trên CPU Intel) nếu đã chạy
export_openvino.py, không có thì dùng file .pt.
"""
from pathlib import Path

from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"

# Các file bắt buộc phải có (model pose có thể tự tải về nên không nằm trong danh sách này)
REQUIRED_MODELS = [
    "train_myself-cheat_paper.pt",
    "train_myself-phone_and_laptop2.pt",
]


def check_required_models():
    """Báo lỗi rõ ràng nếu thiếu file model trong thư mục models/."""
    from config.config import Config
    required = list(REQUIRED_MODELS) + (["phone_detection.pt"] if Config.USE_INCAR_PHONE_MODEL else [])
    missing = [n for n in required if not (MODEL_DIR / n).exists()]
    if missing:
        raise FileNotFoundError(
            f"Thiếu file model trong thư mục {MODEL_DIR}: {', '.join(missing)}. "
            "Hãy chép các file .pt vào thư mục models/ của project."
        )


def _exported_imgsz(ov_dir: Path):
    """Đọc kích thước ảnh mà bản OpenVINO đã được xuất (metadata.yaml). None nếu không đọc được."""
    try:
        import yaml
        meta = yaml.safe_load((ov_dir / "metadata.yaml").read_text(encoding="utf-8"))
        size = meta.get("imgsz")
        return int(size[0] if isinstance(size, (list, tuple)) else size)
    except Exception:
        return None


# Cache lưu trữ các model đã nạp vào bộ nhớ để tránh phải đọc lại từ ổ đĩa
_MODEL_CACHE = {}


def load_yolo(filename: str, task: str, imgsz: int = None):
    """Ưu tiên models/<tên>_openvino_model, lỗi thì quay về file .pt.
    imgsz: kích thước dự định chạy; nếu bản OpenVINO xuất ở kích thước khác thì bỏ qua nó (tránh lỗi shape)."""
    cache_key = (filename, task, imgsz)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    ov_dir = MODEL_DIR / (Path(filename).stem + "_openvino_model")
    if ov_dir.exists() and imgsz is not None:
        exported = _exported_imgsz(ov_dir)
        if exported is not None and exported != imgsz:
            print(f"[ModelLoader] {ov_dir.name} xuất ở {exported}px nhưng cấu hình là {imgsz}px -> dùng file .pt. "
                  f"Chạy lại export_openvino.py để dùng OpenVINO.")
            ov_dir = Path("__không_dùng__")
    if ov_dir.exists():
        try:
            print(f"[ModelLoader] OpenVINO: {ov_dir.name}")
            model = YOLO(str(ov_dir), task=task)
            _MODEL_CACHE[cache_key] = model
            return model
        except Exception as exc:
            print(f"[ModelLoader] Không nạp được {ov_dir.name} ({exc}), dùng file .pt")
    pt = MODEL_DIR / filename
    model = YOLO(str(pt) if pt.exists() else filename)
    _MODEL_CACHE[cache_key] = model
    return model
