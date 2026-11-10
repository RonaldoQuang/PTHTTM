"""
tools/train_objects.py
----------------------
Train MỘT model vật thể 2 lớp (phone, cheat_paper) thay cho 3 model rời.
Chạy trên Colab (GPU T4 miễn phí) hoặc máy có GPU; trên CPU sẽ rất chậm.

  pip install ultralytics
  python tools/train_objects.py --data /path/to/data.yaml --epochs 80

--data : data.yaml export từ Roboflow (YOLOv11). Class phải là: phone, cheat_paper (tên chứa 'phone' và 'paper' được hệ thống nhận). Có thể GỘP ảnh Roboflow công khai + ảnh của bạn trong cùng project.
Xong sẽ in đường dẫn best.pt. Chép file đó vào  exam_proctor/models/train_myself-objects_v3.pt
(đúng tên trong config: Config.OBJECT_MODEL_FILE) rồi chạy lại export_openvino.py. Hệ thống tự dùng model mới.
"""
import argparse

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--base", default="yolo11n.pt", help="model nền (mặc định yolo11n: nhỏ, hợp để chạy trên CPU)")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=640, help="phải khớp EXPORT_IMGSZ trong export_openvino.py")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--patience", type=int, default=20, help="dừng sớm nếu không cải thiện sau N epoch")
    args = ap.parse_args()

    model = YOLO(args.base)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                patience=args.patience, project="runs_objects", name="v3", exist_ok=True)
    metrics = model.val()
    print("\n=== KẾT QUẢ TRÊN TẬP VALID ===")
    print(f"mAP50 = {metrics.box.map50:.3f} | mAP50-95 = {metrics.box.map:.3f}")
    for i, name in model.names.items():
        print(f"  {name:12s} P={metrics.box.p[i]:.3f}  R={metrics.box.r[i]:.3f}  mAP50={metrics.box.ap50[i]:.3f}")
    print("\nFile model tốt nhất: runs_objects/v3/weights/best.pt")
    print("Chép thành exam_proctor/models/train_myself-objects_v3.pt")


if __name__ == "__main__":
    main()
