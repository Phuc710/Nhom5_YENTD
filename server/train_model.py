"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TRAIN MODEL RIÊNG — YOLOv8n / YOLOv8s                                     ║
║  Hệ thống phát hiện xe vượt đèn đỏ                                         ║
║                                                                              ║
║  CHẠY:                                                                       ║
║    python train_model.py                  ← train YOLOv8n (nano, nhanh)     ║
║    python train_model.py --model s        ← train YOLOv8s (nhỏ, tốt hơn)   ║
║    python train_model.py --resume        ← tiếp tục train bị gián đoạn     ║
║    python train_model.py --validate      ← chỉ đánh giá, không train       ║
║    python train_model.py --export        ← xuất sang ONNX sau khi train    ║
║                                                                              ║
║  KẾT QUẢ:                                                                   ║
║    runs/traffic/traffic_yolov8n/weights/best.pt  ← dùng cái này            ║
║    runs/traffic/traffic_yolov8n/weights/last.pt                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import os
import sys
import shutil
import time
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# KIỂM TRA THƯ VIỆN
# ─────────────────────────────────────────────────────────────────────────────
try:
    from ultralytics import YOLO
    import torch
except ImportError:
    print("❌ Chưa cài thư viện. Chạy lệnh sau:")
    print("   pip install ultralytics torch torchvision")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# CẤU HÌNH TRAINING
# ─────────────────────────────────────────────────────────────────────────────

# Thư mục gốc (cùng chỗ với file này)
BASE_DIR    = Path(__file__).resolve().parent
DATA_YAML   = BASE_DIR / "traffic_data.yaml"
DATASET_DIR = BASE_DIR / "dataset"
RUNS_DIR    = BASE_DIR / "runs" / "traffic"

# Tên project theo thời gian để dễ phân biệt
TIMESTAMP   = datetime.now().strftime("%m%d_%H%M")


def resolve_data_source(data_arg: str) -> tuple[str, bool, str]:
    """Resolve dataset config and whether it is the built-in traffic dataset."""
    raw = (data_arg or "").strip()
    if not raw:
        return str(DATA_YAML), True, "traffic"

    candidate = Path(raw)
    if candidate.exists():
        return str(candidate.resolve()), False, candidate.stem

    return raw, False, Path(raw).stem or "external"

# ─────────────────────────────────────────────────────────────────────────────
# CẤU HÌNH 7 GIỚI HẠN NGỮ CẢNH (khớp với hệ thống ESP32)
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_LIMITS = {
    "speed_kmh":        20,      # GH1: < 20 km/h
    "vehicles_frame":   6,       # GH2: ≤ 6 xe/frame
    "weather":          ["SUN", "LIGHT_RAIN", "CLOUDY"],  # GH3
    "distance_m":       5,       # GH4: 5m
    "roi":              "STOP_LINE",  # GH5
    "capture_ms":       500,     # GH6: 500ms, chỉ khi ĐỎ
    "targets":          ["motorbike", "car"],  # GH7
}

# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 1 — TẠO FILE traffic_data.yaml
# ─────────────────────────────────────────────────────────────────────────────

TRAFFIC_DATA_YAML_CONTENT = """\
# ════════════════════════════════════════════════════════
# TRAFFIC VIOLATION DETECTION — DATASET CONFIG
# 7 classes: xe + đèn giao thông
# ════════════════════════════════════════════════════════

train: dataset/images/train
val:   dataset/images/val

# Số class
nc: 7

# Tên class (thứ tự phải khớp với file nhãn .txt)
names:
  0: motorbike           # GH7: Xe máy
  1: car                 # GH7: Ô tô
  2: truck               # Xe tải
  3: bus                 # Xe buýt
  4: traffic_light_red   # Đèn đỏ
  5: traffic_light_yellow  # Đèn vàng
  6: traffic_light_green   # Đèn xanh
"""

# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 2 — TẠO CẤU TRÚC THƯ MỤC DATASET
# ─────────────────────────────────────────────────────────────────────────────

def create_dataset_structure():
    """Tạo thư mục dataset đúng chuẩn YOLO."""
    folders = [
        DATASET_DIR / "images" / "train",
        DATASET_DIR / "images" / "val",
        DATASET_DIR / "labels" / "train",
        DATASET_DIR / "labels" / "val",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    # Ghi file hướng dẫn vào thư mục ảnh
    guide = DATASET_DIR / "images" / "train" / "README.txt"
    guide.write_text(
        "Đặt ảnh .jpg hoặc .png vào đây.\n"
        "File nhãn tương ứng đặt vào: dataset/labels/train/<tên_ảnh>.txt\n\n"
        "Format nhãn YOLO (mỗi dòng = 1 vật thể):\n"
        "<class_id> <cx> <cy> <width> <height>\n"
        "Tất cả giá trị cx/cy/width/height đều được chuẩn hóa về [0, 1]\n\n"
        "Class IDs:\n"
        "  0: motorbike\n"
        "  1: car\n"
        "  2: truck\n"
        "  3: bus\n"
        "  4: traffic_light_red\n"
        "  5: traffic_light_yellow\n"
        "  6: traffic_light_green\n",
        encoding="utf-8"
    )
    print("✅ Tạo cấu trúc thư mục dataset/")
    print("   📁 dataset/images/train/   ← đặt ảnh train vào đây")
    print("   📁 dataset/images/val/     ← đặt ảnh val vào đây")
    print("   📁 dataset/labels/train/   ← file nhãn .txt tương ứng")
    print("   📁 dataset/labels/val/     ← file nhãn .txt tương ứng")


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 3 — KIỂM TRA MÔI TRƯỜNG TRƯỚC KHI TRAIN
# ─────────────────────────────────────────────────────────────────────────────

def check_environment(model_size: str = "n", data_config: str | None = None, builtin_dataset: bool = True) -> dict:
    """Kiểm tra GPU, RAM, dataset trước khi train."""
    print("\n" + "═" * 60)
    print("  KIỂM TRA MÔI TRƯỜNG TRAINING")
    print("═" * 60)

    info = {}

    # GPU
    if torch.cuda.is_available():
        gpu_name  = torch.cuda.get_device_name(0)
        gpu_vram  = torch.cuda.get_device_properties(0).total_memory / 1024**3
        info["device"] = "0"
        info["gpu"]    = gpu_name
        info["vram_gb"] = round(gpu_vram, 1)
        print(f"  ✅ GPU: {gpu_name} ({gpu_vram:.1f} GB VRAM)")

        # Khuyến nghị batch size theo VRAM
        if gpu_vram >= 8:
            info["batch"] = 32
        elif gpu_vram >= 4:
            info["batch"] = 16
        else:
            info["batch"] = 8
    else:
        info["device"] = "cpu"
        info["gpu"]    = "Không có GPU"
        info["batch"]  = 4
        print("  ⚠️  Không có GPU — train bằng CPU (rất chậm)")
        print("       Ước tính: ~2–4 giờ/epoch với dataset nhỏ")

    print(f"  📦 Batch size đề xuất: {info['batch']}")

    # PyTorch version
    print(f"  🔧 PyTorch: {torch.__version__}")

    # Dataset
    if not builtin_dataset:
        info["train_count"] = "external"
        info["val_count"]   = "external"
        info["dataset_ok"]  = True
        print("  🌐 Dataset: external/public")
        print(f"     Data config: {data_config}")
    else:
        train_imgs = list((DATASET_DIR / "images" / "train").glob("*.jpg")) + \
                     list((DATASET_DIR / "images" / "train").glob("*.png"))
        val_imgs   = list((DATASET_DIR / "images" / "val").glob("*.jpg")) + \
                     list((DATASET_DIR / "images" / "val").glob("*.png"))

        info["train_count"] = len(train_imgs)
        info["val_count"]   = len(val_imgs)

        if len(train_imgs) == 0:
            print(f"\n  ❌ Chưa có ảnh trong dataset/images/train/")
            print("     Xem hướng dẫn trong file README.txt vừa tạo")
            info["dataset_ok"] = False
        else:
            print(f"  🖼️  Ảnh train: {len(train_imgs)} ảnh")
            print(f"  🖼️  Ảnh val:   {len(val_imgs)} ảnh")
            info["dataset_ok"] = True

    # traffic_data.yaml
    if builtin_dataset:
        if DATA_YAML.exists():
            print(f"  ✅ traffic_data.yaml: OK")
            info["yaml_ok"] = True
        else:
            print(f"  ❌ Thiếu traffic_data.yaml — sẽ tạo tự động")
            info["yaml_ok"] = False
    else:
        info["yaml_ok"] = True

    print("═" * 60)
    return info


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 4 — HÀM TRAIN CHÍNH
# ─────────────────────────────────────────────────────────────────────────────

def train(
    model_size:  str  = "n",      # "n" = nano, "s" = small
    epochs:      int  = 100,
    imgsz:       int  = 640,
    batch:       int  = 16,
    device:      str  = "0",
    resume:      bool = False,
    patience:    int  = 30,       # Early stopping: dừng nếu không cải thiện
    data_config: str  = str(DATA_YAML),
    dataset_label: str = "traffic",
) -> Path:
    """
    Train YOLOv8n hoặc YOLOv8s với traffic dataset.

    Trả về đường dẫn đến best.pt.
    """

    model_name    = f"yolov8{model_size}.pt"
    model_path    = BASE_DIR / model_name
    model_source  = str(model_path) if model_path.exists() else model_name
    project_name  = f"{dataset_label}_yolov8{model_size}_{TIMESTAMP}"
    best_pt_path  = RUNS_DIR / project_name / "weights" / "best.pt"

    print(f"\n{'═'*60}")
    print(f"  BẮT ĐẦU TRAINING — YOLOv8{model_size.upper()}")
    print(f"  Model:   {model_source}")
    print(f"  Epochs:  {epochs}")
    print(f"  Imgsz:   {imgsz}x{imgsz}")
    print(f"  Batch:   {batch}")
    print(f"  Device:  {'GPU cuda:' + device if device != 'cpu' else 'CPU'}")
    print(f"  Output:  {best_pt_path}")
    print(f"{'═'*60}\n")

    # Load model
    if resume:
        # Tìm last.pt gần nhất để tiếp tục
        last_pts = sorted(RUNS_DIR.rglob("last.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not last_pts:
            print("❌ Không tìm thấy last.pt để resume. Bắt đầu train mới.")
            resume = False
            model = YOLO(model_source)
        else:
            last_pt = last_pts[0]
            print(f"▶️  Resume từ: {last_pt}")
            model = YOLO(str(last_pt))
    else:
        model = YOLO(model_source)
        print(f"✅ Tải pretrained weights: {model_source}")

    # ── BẮT ĐẦU TRAIN ────────────────────────────────────────────────────────
    start_time = time.time()

    results = model.train(
        data        = str(data_config),
        epochs      = epochs,
        imgsz       = imgsz,
        batch       = batch,
        device      = device,
        project     = str(RUNS_DIR),
        name        = project_name,
        resume      = resume,
        patience    = patience,    # Early stopping

        # ── Augmentation tối ưu cho camera giao thông cố định ────────────────
        hsv_h       = 0.015,   # Hue: nhẹ — đèn giao thông nhạy màu
        hsv_s       = 0.7,     # Saturation: biến đổi điều kiện sáng GH3
        hsv_v       = 0.4,     # Brightness: nắng → mưa nhẹ GH3
        degrees     = 0.0,     # Không xoay — camera CỐ ĐỊNH GH5
        translate   = 0.1,     # Dịch chuyển nhẹ
        scale       = 0.5,     # Scale: mô phỏng xe xa/gần GH4
        flipud      = 0.0,     # KHÔNG flip dọc — xe trên đường
        fliplr      = 0.5,     # Flip ngang: 2 chiều làn đường
        mosaic      = 1.0,     # Mosaic: tăng đa dạng dataset
        mixup       = 0.0,     # MixUp: tắt — tránh nhầm màu đèn
        copy_paste  = 0.1,     # Copy-paste: thêm xe vào scene

        # ── Tham số optimizer ────────────────────────────────────────────────
        optimizer   = "AdamW",
        lr0         = 0.001,   # Learning rate ban đầu
        lrf         = 0.01,    # Learning rate cuối = lr0 * lrf
        momentum    = 0.937,
        weight_decay= 0.0005,
        warmup_epochs = 3.0,

        # ── Ngưỡng phát hiện ─────────────────────────────────────────────────
        conf        = 0.001,   # Ngưỡng confidence khi train (thấp để học tốt)
        iou         = 0.7,     # NMS IoU threshold

        # ── Lưu kết quả ──────────────────────────────────────────────────────
        save        = True,
        save_period = 10,      # Lưu checkpoint mỗi 10 epoch
        plots       = True,    # Vẽ biểu đồ training
        verbose     = True,
    )

    elapsed = time.time() - start_time
    hours   = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)

    print(f"\n{'═'*60}")
    print(f"  ✅ TRAINING HOÀN TẤT!")
    print(f"  ⏱️  Thời gian: {hours}h {minutes}m")
    print(f"  📁 Best model: {best_pt_path}")
    print(f"{'═'*60}")

    return best_pt_path


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 5 — ĐÁNH GIÁ MODEL SAU TRAIN
# ─────────────────────────────────────────────────────────────────────────────

def validate(model_pt: str | Path, data_config: str | Path = DATA_YAML) -> dict:
    """
    Đánh giá model trên tập val.
    Trả về metrics: mAP50, mAP50-95, precision, recall.
    """
    print(f"\n{'═'*60}")
    print(f"  ĐÁNH GIÁ MODEL")
    print(f"  Model: {model_pt}")
    print(f"{'═'*60}\n")

    model   = YOLO(str(model_pt))
    metrics = model.val(
        data  = str(data_config),
        imgsz = 640,
        conf  = 0.40,   # Ngưỡng confidence khi đánh giá
        iou   = 0.50,
    )

    result = {
        "mAP50":     round(float(metrics.box.map50), 4),
        "mAP50-95":  round(float(metrics.box.map),   4),
        "precision": round(float(metrics.box.mp),    4),
        "recall":    round(float(metrics.box.mr),    4),
    }

    print(f"\n  📊 KẾT QUẢ ĐÁNH GIÁ:")
    print(f"     mAP50:     {result['mAP50'] * 100:.1f}%  (mục tiêu > 80%)")
    print(f"     mAP50-95:  {result['mAP50-95'] * 100:.1f}%")
    print(f"     Precision: {result['precision'] * 100:.1f}%  (ít bắt nhầm)")
    print(f"     Recall:    {result['recall'] * 100:.1f}%  (ít bỏ sót)")

    # Nhận xét tự động
    print("\n  📝 NHẬN XÉT:")
    if result["mAP50"] >= 0.80:
        print("     ✅ Model tốt — đủ điều kiện deploy vào hệ thống")
    elif result["mAP50"] >= 0.65:
        print("     ⚠️  Model ổn — nên thêm data và train thêm 50 epoch")
    else:
        print("     ❌ Model yếu — cần thêm nhiều ảnh hơn hoặc kiểm tra nhãn")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 6 — XUẤT MODEL SANG ONNX (tuỳ chọn)
# ─────────────────────────────────────────────────────────────────────────────

def export_to_onnx(model_pt: str | Path) -> str:
    """
    Xuất .pt → .onnx để deploy không cần PyTorch.
    Dùng khi muốn chạy trên server không có CUDA.
    """
    print(f"\n  📦 Xuất ONNX: {model_pt}")
    model = YOLO(str(model_pt))
    path  = model.export(
        format  = "onnx",
        dynamic = True,    # Hỗ trợ batch size linh động
        simplify= True,    # Đơn giản hoá graph
        imgsz   = 640,
    )
    print(f"  ✅ ONNX đã xuất: {path}")
    return str(path)


# ─────────────────────────────────────────────────────────────────────────────
# BƯỚC 7 — SAO CHÉP best.pt VÀO THƯ MỤC GỐC
# ─────────────────────────────────────────────────────────────────────────────

def copy_best_to_root(best_pt: Path, model_size: str = "n") -> Path:
    """
    Sao chép best.pt ra thư mục gốc với tên chuẩn
    để app.py và yolov8n_engine.py tự tìm thấy.
    """
    dest_name = f"traffic_yolov8{model_size}_best.pt"
    dest      = BASE_DIR / dest_name

    if best_pt.exists():
        shutil.copy2(str(best_pt), str(dest))
        print(f"\n  ✅ Đã copy best.pt → {dest_name}")
        print(f"     app.py và yolov8n_engine.py sẽ tự động dùng file này")
    else:
        print(f"\n  ❌ Không tìm thấy {best_pt}")

    return dest


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Train YOLOv8n/s cho hệ thống phát hiện xe vượt đèn đỏ"
    )
    parser.add_argument(
        "--model", choices=["n", "s"], default="n",
        help="Kích thước model: n=nano (nhanh), s=small (tốt hơn)"
    )
    parser.add_argument("--epochs",   type=int, default=100, help="Số epoch (mặc định 100)")
    parser.add_argument("--batch",    type=int, default=0,   help="Batch size (0 = tự động)")
    parser.add_argument("--imgsz",    type=int, default=640, help="Kích thước ảnh (mặc định 640)")
    parser.add_argument("--resume",   action="store_true",   help="Tiếp tục train bị gián đoạn")
    parser.add_argument("--validate", action="store_true",   help="Chỉ đánh giá, không train")
    parser.add_argument("--export",   action="store_true",   help="Xuất ONNX sau khi train")
    parser.add_argument("--model-pt", type=str, default="",  help="Đường dẫn .pt để validate/export")
    parser.add_argument("--patience", type=int, default=30,  help="Early stopping patience")
    parser.add_argument(
        "--data", type=str, default="",
        help="Dataset YAML/preset. Ví dụ: coco8.yaml hoặc C:\\dataset\\data.yaml"
    )
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  AI TRAFFIC VIOLATION — TRAIN MODEL")
    print(f"  {datetime.now().strftime('%d/%m/%Y  %H:%M:%S')}")
    print("═" * 60)

    # ── Tạo file yaml nếu chưa có ────────────────────────────────────────────
    if not DATA_YAML.exists():
        DATA_YAML.write_text(TRAFFIC_DATA_YAML_CONTENT, encoding="utf-8")
        print(f"✅ Tạo traffic_data.yaml")

    # ── Tạo cấu trúc dataset ─────────────────────────────────────────────────
    create_dataset_structure()

    # ── Kiểm tra môi trường ──────────────────────────────────────────────────
    env = check_environment(args.model)
    data_config, builtin_dataset, dataset_label = resolve_data_source(args.data)
    if not builtin_dataset:
        print(f"🌐 Dùng dataset public/external: {data_config}")
        env["dataset_ok"] = True
        env["yaml_ok"] = True
        env["train_count"] = "external"
        env["val_count"] = "external"

    # ── Xác định device và batch ─────────────────────────────────────────────
    device = env["device"]
    batch  = args.batch if args.batch > 0 else env["batch"]

    # ── Chế độ validate chỉ ──────────────────────────────────────────────────
    if args.validate:
        pt = args.model_pt
        if not pt:
            # Tự tìm best.pt gần nhất
            pts = sorted(RUNS_DIR.rglob("best.pt"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
            if not pts:
                print("❌ Không tìm thấy best.pt. Hãy train trước.")
                sys.exit(1)
            pt = str(pts[0])
            print(f"🔍 Dùng model gần nhất: {pt}")
        validate(pt, data_config=data_config)
        return

    # ── Kiểm tra dataset có ảnh chưa ─────────────────────────────────────────
    if builtin_dataset and not env.get("dataset_ok"):
        print("\n⛔ DỪNG: Chưa có ảnh trong dataset/images/train/")
        print("\n📌 HƯỚNG DẪN LẤY DATASET:")
        print("   1. Tải từ Roboflow: https://universe.roboflow.com")
        print('      Search: "vietnam traffic violation" hoặc "motorbike car detection"')
        print("      Export format: YOLOv8 → tải về → giải nén vào thư mục dataset/")
        print()
        print("   2. Tự gán nhãn bằng LabelImg:")
        print("      pip install labelImg")
        print("      labelImg dataset/images/train  dataset/classes.txt")
        print()
        print("   3. Dataset công khai khuyến nghị:")
        print("      - COCO 2017 (có car, motorcycle, bus, truck)")
        print("      - VisDrone (drone traffic, có xe VN)")
        print("      - UA-DETRAC (vehicle detection)")
        sys.exit(0)

    # ── TRAIN ────────────────────────────────────────────────────────────────
    best_pt = train(
        model_size = args.model,
        epochs     = args.epochs,
        imgsz      = args.imgsz,
        batch      = batch,
        device     = device,
        resume     = args.resume,
        patience   = args.patience,
        data_config= data_config,
        dataset_label= dataset_label,
    )

    # ── ĐÁNH GIÁ SAU TRAIN ───────────────────────────────────────────────────
    if best_pt.exists():
        metrics = validate(best_pt, data_config=data_config)

        # ── SAO CHÉP VỀ THƯ MỤC GỐC ─────────────────────────────────────────
        if builtin_dataset:
            copy_best_to_root(best_pt, args.model)
        else:
            print("\n  ℹ️  Dataset public/external — không copy đè model traffic production")

        # ── XUẤT ONNX ────────────────────────────────────────────────────────
        if args.export:
            export_to_onnx(best_pt)

        # ── TỔNG KẾT ─────────────────────────────────────────────────────────
        print(f"\n{'═'*60}")
        print("  TỔNG KẾT")
        print(f"{'═'*60}")
        print(f"  Model:     YOLOv8{args.model.upper()}")
        print(f"  mAP50:     {metrics['mAP50']*100:.1f}%")
        print(f"  Precision: {metrics['precision']*100:.1f}%")
        print(f"  Recall:    {metrics['recall']*100:.1f}%")
        if builtin_dataset:
            print(f"  File:      traffic_yolov8{args.model}_best.pt")
        else:
            print(f"  File:      {best_pt.name}")
        print()
        print("  ▶️  BƯỚC TIẾP THEO:")
        if builtin_dataset:
            print(f"     Đặt file traffic_yolov8{args.model}_best.pt vào cùng thư mục app.py")
            print("     Khởi động: python server/app.py")
        else:
            print("     Đây là model test pipeline, chưa nên gắn vào app.py production")
        print(f"{'═'*60}\n")
    else:
        print("❌ Không tìm thấy best.pt sau khi train")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
