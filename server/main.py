import argparse

import configs.settings as cfg
from src.vehicle_counter import VehicleCounterPro, setup_logging

"""
NOTE:
- This entrypoint is for standalone AI video-counting experiments.
- Production backend runtime uses `server/app.py` (FastAPI).
- Do not run this module as part of production service startup.
"""


def build_parser():
    """
    Tao bo parser tham so dong lenh.

    Loi ich cua argparse:
    - Khong can mo code de doi video.
    - Chay nhieu video lien tuc cuc nhanh.
    - Rat hop phong cach van hanh cua mot project nghiem tuc.
    """
    parser = argparse.ArgumentParser(
        description="He thong dem xe bang YOLOv8 + tracking + line crossing"
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(cfg.DEFAULT_VIDEO_PATH),
        help="Duong dan toi video dau vao",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(cfg.DEFAULT_MODEL_PATH),
        help="Duong dan toi model YOLOv8",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Duong dan toi video output. Neu bo trong se tu sinh ten file",
    )
    parser.add_argument(
        "--save-output",
        action="store_true",
        help="Bat che do luu video ket qua vao data/outputs",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Khong mo cua so hien thi. Huu ich khi chay tren may khong co man hinh",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=cfg.CONFIDENCE_THRESHOLD,
        help="Nguong confidence cho detector",
    )
    parser.add_argument(
        "--tracker",
        type=str,
        default=cfg.TRACKER_TYPE,
        help="Ten file tracker cua Ultralytics, vi du bytetrack.yaml hoac botsort.yaml",
    )
    return parser


def main():
    cfg.ensure_project_dirs()
    logger = setup_logging()

    parser = build_parser()
    args = parser.parse_args()

    logger.info("Tham so chay: %s", vars(args))

    counter = VehicleCounterPro(
        model_path=args.model,
        confidence=args.conf,
        tracker=args.tracker,
    )
    result = counter.run(
        video_path=args.video,
        output_path=args.output,
        save_output=args.save_output,
        show_window=not args.no_show,
    )

    logger.info("Ket qua cuoi cung: %s", result)


if __name__ == "__main__":
    main()
