"""
evaluate.py - Đánh giá hệ thống trên 1 video phòng thi (không cần chạy web, không cần DB).

BƯỚC 1: chạy hệ thống trên video, xuất các cảnh báo + tốc độ xử lý
    python evaluate.py            (chạy trơn: tự hỏi/mở cửa sổ chọn video)
   hoặc:
    python evaluate.py run video.mp4
        --stride 2        (xử lý 1 trong mỗi 2 frame cho nhanh; mặc định 2)
        --max-sec 180     (chỉ xử lý N giây đầu; mặc định cả video)
    -> tạo predictions.csv và in bảng tóm tắt (FPS, số chỗ ngồi, số cảnh báo từng loại)

BƯỚC 2: tự xem video, ghi các sự kiện THẬT vào ground_truth.csv (xem ground_truth_example.csv):
    start_sec,end_sec,type
    12,18,QUAY DAU
    40,55,mobile_phone
    (type là một trong: QUAY DAU, CUI GAM MAT, CUI DAU THAP, GIO TAY CAO, NAM RA BAN, DUNG DAY,
     mobile_phone, cheat_paper, laptop)

BƯỚC 2 (NHANH, chỉ đo precision): xem ảnh từng cảnh báo và bấm Đúng/Sai
    python evaluate.py review video.mp4 predictions.csv
    -> tạo review.html: mở bằng trình duyệt, bấm Đúng/Sai, bấm "Sao chép kết quả" rồi gửi lại

BƯỚC 3: so sánh
    python evaluate.py score predictions.csv ground_truth.csv --tol 3
    -> in precision / recall từng loại cảnh báo

Cách tính (đơn giản, nói rõ khi báo cáo): một cảnh báo của hệ thống được tính ĐÚNG nếu cùng loại và nằm trong
khoảng [start - tol, end + tol] của một sự kiện thật. Một sự kiện thật được tính BẮT ĐƯỢC nếu có ít nhất
một cảnh báo đúng. Không so khớp số chỗ ngồi.
"""
import argparse
import csv
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))


def run(args):
    import cv2
    from core.incident_recorder import IncidentRecorder
    from core.monitoring_service import MonitoringService

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"Không mở được video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    max_frames = int(args.max_sec * fps) if args.max_sec else total or 10 ** 9
    print(f"Video: {total} frame, {fps:.1f} fps gốc, ~{total / fps:.0f} giây. Xử lý 1/{args.stride} frame.")

    rows = []

    class ListRecorder(IncidentRecorder):
        """Không ghi DB/ảnh: chỉ ghi lại cảnh báo (kèm cooldown) vào danh sách rows."""
        def __init__(self):
            super().__init__(db=None, exam_id=0)

        def save(self, raw, scale, seat, warning, conf=0.0, bbox=None, now=0.0):
            if seat is None or not self.should_record(seat, warning, now):
                return
            box = [int(v * scale) for v in bbox] if bbox is not None else ["", "", "", ""]
            rows.append((round(now, 2), seat, warning, round(float(conf), 3), *box))

    class OfflineService(MonitoringService):
        idx = -1
        cur_t = 0.0
        proc_times = []

        def _clock(self):
            return self.cur_t              # dùng THỜI GIAN CỦA VIDEO, không phải giờ máy

        def _next_frame(self):
            t0 = getattr(self, "_t_last", None)
            if t0 is not None:
                self.proc_times.append(time.time() - t0)
            while True:
                ok, frame = cap.read()
                self.idx += 1
                if not ok or self.idx >= max_frames:
                    self.is_running = False
                    return False, None
                if self.idx % args.stride == 0:
                    break
            self.cur_t = self.idx / fps
            self._t_last = time.time()
            if self.idx % (args.stride * 30) == 0:
                print(f"  ... {self.cur_t:5.0f}s / {min(total, max_frames) / fps:.0f}s", flush=True)
            return True, frame

    svc = OfflineService(db_manager=None, recorder=ListRecorder())
    svc.is_running = True
    svc._process_loop()          # chạy ngay trong luồng chính, đọc frame từ video
    cap.release()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["video_sec", "seat", "type", "conf", "x1", "y1", "x2", "y2"])
        w.writerows(rows)

    pt = svc.proc_times
    avg = sum(pt) / len(pt) if pt else 0
    print("\n===== TÓM TẮT (gửi lại phần này) =====")
    print(f"Số frame đã xử lý: {len(pt)} | thời gian xử lý trung bình: {avg * 1000:.0f} ms/frame "
          f"=> {1 / avg if avg else 0:.1f} FPS")
    print(f"Số chỗ ngồi (thí sinh) nhận diện được: {svc.seats.count}")
    print(f"Tổng cảnh báo: {len(rows)}  (ghi vào {args.out})")
    for k, v in Counter(r[2] for r in rows).most_common():
        print(f"  {k:14s} {v}")
    per_seat = Counter(r[1] for r in rows)
    print("Top chỗ nhiều cảnh báo:", per_seat.most_common(5))


def load_pred(path):
    with open(path, encoding="utf-8") as f:
        return [(float(r["video_sec"]), r["type"].strip()) for r in csv.DictReader(f)]


def load_gt(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r.get("type"):
                continue
            out.append((float(r["start_sec"]), float(r["end_sec"]), r["type"].strip()))
    return out


def score(args):
    preds, gts = load_pred(args.pred), load_gt(args.gt)
    types = sorted({t for _, t in preds} | {t for _, _, t in gts})
    print(f"Sai số thời gian cho phép: ±{args.tol}s\n")
    print(f"{'Loại':14s} {'Cảnh báo':>9s} {'Đúng':>5s} {'Precision':>10s} | {'Sự kiện thật':>12s} {'Bắt được':>9s} {'Recall':>7s}")
    tp_all = p_all = g_all = c_all = 0
    for t in types:
        P = [s for s, tt in preds if tt == t]
        G = [(a, b) for a, b, tt in gts if tt == t]
        tp = sum(1 for s in P if any(a - args.tol <= s <= b + args.tol for a, b in G))
        caught = sum(1 for a, b in G if any(a - args.tol <= s <= b + args.tol for s in P))
        pr = f"{tp / len(P):.0%}" if P else "-"
        rc = f"{caught / len(G):.0%}" if G else "-"
        print(f"{t:14s} {len(P):9d} {tp:5d} {pr:>10s} | {len(G):12d} {caught:9d} {rc:>7s}")
        tp_all += tp; p_all += len(P); g_all += len(G); c_all += caught
    print("-" * 70)
    print(f"{'TỔNG':14s} {p_all:9d} {tp_all:5d} {(tp_all / p_all if p_all else 0):10.0%} | {g_all:12d} {c_all:9d} {(c_all / g_all if g_all else 0):7.0%}")
    print("\nGợi ý: precision thấp = báo nhầm nhiều (tăng ngưỡng/thời gian duy trì); recall thấp = bỏ sót (hạ ngưỡng).")


REVIEW_HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Đánh dấu cảnh báo đúng / sai</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1b1f24;--mut:#6a737d;--bd:#d8dee4;--ok:#1a7f37;--no:#cf222e}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--card:#161b22;--tx:#e6edf3;--mut:#8b949e;--bd:#30363d;--ok:#3fb950;--no:#f85149}}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--bd);padding:10px 16px;z-index:5}
h1{font-size:17px;margin:0 0 6px}table{border-collapse:collapse;font-size:13px}
td,th{padding:2px 10px;border-bottom:1px solid var(--bd);text-align:right}td:first-child,th:first-child{text-align:left}
button{font:inherit;padding:5px 12px;border:1px solid var(--bd);border-radius:6px;background:var(--card);color:var(--tx);cursor:pointer}
button.on-ok{background:var(--ok);color:#fff;border-color:var(--ok)}button.on-no{background:var(--no);color:#fff;border-color:var(--no)}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;padding:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}
.card img{width:100%;display:block}.info{padding:8px 12px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.mut{color:var(--mut);font-size:13px}
</style></head><body>
<header><h1>Đánh dấu từng cảnh báo: hệ thống báo đúng hay sai?</h1>
<div id="sum"></div>
<p><button onclick="copyRes()">Sao chép kết quả</button> <span class="mut" id="msg">Bấm "Đúng" nếu ảnh thực sự có hành vi đó, "Sai" nếu hệ thống báo nhầm. Có thể bỏ qua ảnh không chắc.</span></p></header>
<main id="list"></main>
<script>
const DATA=__DATA__;
const NAMES=__NAMES__;
let st={};try{st=JSON.parse(localStorage.getItem("review_"+DATA.length)||"{}")}catch(e){}
function save(){try{localStorage.setItem("review_"+DATA.length,JSON.stringify(st))}catch(e){}}
function mark(i,v){st[i]=(st[i]===v?null:v);save();render()}
function summary(){const t={};DATA.forEach((d,i)=>{const r=t[d.type]||(t[d.type]={n:0,ok:0,no:0});r.n++;if(st[i]===1)r.ok++;if(st[i]===0)r.no++});return t}
function text(){const t=summary();let s="Loại | Cảnh báo | Đã xem | Đúng | Sai | Precision\\n",A=0,B=0,C=0;
 for(const k in t){const r=t[k],rated=r.ok+r.no;A+=r.ok;B+=r.no;C+=r.n;s+=NAMES[k]+" ("+k+") | "+r.n+" | "+rated+" | "+r.ok+" | "+r.no+" | "+(rated?Math.round(100*r.ok/rated)+"%":"-")+"\\n"}
 s+="TỔNG | "+C+" | "+(A+B)+" | "+A+" | "+B+" | "+((A+B)?Math.round(100*A/(A+B))+"%":"-");
 const L=v=>DATA.map((d,i)=>st[i]===v?d.type+" | chỗ "+d.seat+" | giây "+d.t+" | conf "+d.conf:null).filter(x=>x).join("\\n");
 return s+"\\n\\nCẢNH BÁO SAI:\\n"+(L(0)||"(không có)")+"\\n\\nCẢNH BÁO ĐÚNG:\\n"+(L(1)||"(không có)")}
function render(){const t=summary();let h="<table><tr><th>Loại</th><th>Cảnh báo</th><th>Đã xem</th><th>Đúng</th><th>Sai</th><th>Precision</th></tr>";
 for(const k in t){const r=t[k],rated=r.ok+r.no;h+="<tr><td>"+NAMES[k]+"</td><td>"+r.n+"</td><td>"+rated+"</td><td>"+r.ok+"</td><td>"+r.no+"</td><td>"+(rated?Math.round(100*r.ok/rated)+"%":"-")+"</td></tr>"}
 document.getElementById("sum").innerHTML=h+"</table>";
 document.getElementById("list").innerHTML=DATA.map((d,i)=>`<div class="card"><img src="data:image/jpeg;base64,${d.img}" alt="">
 <div class="info"><div><b>${NAMES[d.type]}</b> <span class="mut">chỗ #${d.seat} · giây ${d.t} · tin cậy ${d.conf}</span></div>
 <div><button class="${st[i]===1?"on-ok":""}" onclick="mark(${i},1)">Đúng</button> <button class="${st[i]===0?"on-no":""}" onclick="mark(${i},0)">Sai</button></div></div></div>`).join("")}
function copyRes(){const s=text();const m=document.getElementById("msg");
 const done=()=>m.textContent="Đã sao chép! Dán vào tin nhắn gửi lại.";
 if(navigator.clipboard){navigator.clipboard.writeText(s).then(done,()=>prompt("Sao chép:",s))}else{prompt("Sao chép:",s)}}
render();
</script></body></html>"""

LABELS_VI = {"QUAY DAU": "Quay đầu", "CUI GAM MAT": "Cúi gằm mặt", "CUI DAU THAP": "Cúi đầu thấp",
             "GIO TAY CAO": "Giơ tay cao", "NAM RA BAN": "Nằm ra bàn", "DUNG DAY": "Đứng dậy",
             "mobile_phone": "Điện thoại", "cheat_paper": "Phao thi", "laptop": "Laptop"}


def review(args):
    """Tạo review.html: ảnh từng cảnh báo (cắt từ video) + nút Đúng/Sai, tự tính precision từng loại."""
    import base64
    import json
    import cv2
    from core.incident_recorder import build_evidence

    with open(args.pred, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("predictions.csv không có cảnh báo nào.")
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"Không mở được video: {args.video}")
    data = []
    for i, r in enumerate(rows):
        t = float(r["video_sec"])
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        try:
            bbox = [int(r[k]) for k in ("x1", "y1", "x2", "y2")]
            frame = build_evidence(frame, 1.0, bbox, LABELS_VI.get(r["type"], r["type"]))
        except (KeyError, ValueError):
            pass   # predictions.csv cũ không có khung: dùng cả frame
        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, int(h * 640 / w)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        data.append({"t": round(t, 1), "seat": r["seat"], "type": r["type"], "conf": r["conf"],
                     "img": base64.b64encode(buf).decode()})
        if (i + 1) % 10 == 0:
            print(f"  ... {i + 1}/{len(rows)}", flush=True)
    cap.release()
    names = {d["type"]: LABELS_VI.get(d["type"], d["type"]) for d in data}
    html = REVIEW_HTML.replace("__DATA__", json.dumps(data)).replace("__NAMES__", json.dumps(names, ensure_ascii=False))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nĐã tạo {args.out} ({len(data)} cảnh báo). Mở file này bằng trình duyệt (bấm đúp) và đánh dấu Đúng/Sai.")


def ask_file(title, filetypes, default=None):
    """Mở cửa sổ chọn file (nếu máy có tkinter), không được thì hỏi gõ/dán đường dẫn."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        if path:
            return path
    except Exception:
        pass
    hint = f" [Enter = {default}]" if default else ""
    path = input(f"{title}{hint}\nDán đường dẫn file vào đây: ").strip().strip('"').strip("'")
    return path or default


def ask_number(prompt, default, cast=float):
    raw = input(f"{prompt} [Enter = {default}]: ").strip()
    try:
        return cast(raw) if raw else default
    except ValueError:
        return default


def interactive():
    """Chạy không kèm tham số: hỏi từng bước (chọn video, ...)."""
    print("=== ĐÁNH GIÁ HỆ THỐNG GIÁM SÁT PHÒNG THI ===")
    print("1) Chạy hệ thống trên 1 video (tạo predictions.csv)")
    print("2) Tính precision / recall (cần predictions.csv và ground_truth.csv)")
    print("3) Xem ảnh từng cảnh báo và bấm Đúng/Sai (tạo review.html, cần predictions.csv + video)")
    choice = input("Chọn 1, 2 hoặc 3 [Enter = 1]: ").strip() or "1"
    if choice == "3":
        video = ask_file("Chọn file video đã dùng ở bước 1", [("Video", "*.mp4 *.avi *.mov *.mkv *.webm"), ("Tất cả", "*.*")])
        pred = ask_file("Chọn file predictions.csv", [("CSV", "*.csv")], "predictions.csv")
        if not video:
            sys.exit("Chưa chọn video.")
        review(argparse.Namespace(video=video, pred=pred, out="review.html"))
    elif choice == "2":
        pred = ask_file("Chọn file predictions.csv", [("CSV", "*.csv")], "predictions.csv")
        gt = ask_file("Chọn file ground_truth.csv", [("CSV", "*.csv")], "ground_truth.csv")
        tol = ask_number("Sai số thời gian cho phép (giây)", 3.0)
        score(argparse.Namespace(pred=pred, gt=gt, tol=tol))
    else:
        video = ask_file("Chọn file video phòng thi",
                         [("Video", "*.mp4 *.avi *.mov *.mkv *.webm"), ("Tất cả", "*.*")])
        if not video:
            sys.exit("Chưa chọn video.")
        stride = ask_number("Xử lý 1 trong mỗi N frame (N càng lớn càng nhanh)", 2, int)
        max_sec = ask_number("Chỉ xử lý N giây đầu (0 = cả video)", 0.0)
        run(argparse.Namespace(video=video, stride=stride, max_sec=max_sec, out="predictions.csv"))
    input("\nXong. Nhấn Enter để đóng...")


def main():
    if len(sys.argv) == 1:      # bấm đúp / chạy trơn: hỏi từng bước
        return interactive()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("video", nargs="?", help="Bỏ trống để mở cửa sổ chọn video")
    r.add_argument("--stride", type=int, default=2); r.add_argument("--max-sec", type=float, default=0)
    r.add_argument("--out", default="predictions.csv")
    v = sub.add_parser("review"); v.add_argument("video"); v.add_argument("pred", nargs="?", default="predictions.csv")
    v.add_argument("--out", default="review.html")
    s = sub.add_parser("score"); s.add_argument("pred"); s.add_argument("gt")
    s.add_argument("--tol", type=float, default=3.0)
    args = ap.parse_args()
    if args.cmd == "run":
        if not args.video:
            args.video = ask_file("Chọn file video phòng thi",
                                  [("Video", "*.mp4 *.avi *.mov *.mkv *.webm"), ("Tất cả", "*.*")])
            if not args.video:
                sys.exit("Chưa chọn video.")
        run(args)
    elif args.cmd == "review":
        review(args)
    else:
        score(args)


if __name__ == "__main__":
    main()
