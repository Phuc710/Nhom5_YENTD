import os
import sys

# Tìm project root (thư mục ytd chứa backend/)
script_dir = os.path.dirname(os.path.abspath(__file__))
# lùi lại 2 cấp từ scripts/ -> backend/ -> ytd/
project_root = os.path.dirname(os.path.dirname(script_dir))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.database.supabase_client import get_supabase_write
from backend.utils.logger import get_logger

logger = get_logger("cleanup")

def delete_all_cameras():
    """Xóa sạch toàn bộ dữ liệu camera và cấu hình."""
    db = get_supabase_write()
    
    try:
        logger.info("🔥 Bắt đầu xóa sạch dữ liệu camera...")
        
        # 1. Xóa Camera Provisioning (Bảng con/liên quan)
        logger.info("- Đang xóa bảng camera_provisioning...")
        db.from_("camera_provisioning").delete().neq("camera_id", 0).execute()
        
        # 2. Xóa Detection Zones
        logger.info("- Đang xóa bảng detection_zones...")
        db.from_("detection_zones").delete().neq("camera_id", 0).execute()
        
        # 3. Xóa Cameras (Bảng chính)
        logger.info("- Đang xóa bảng cameras...")
        db.from_("cameras").delete().neq("camera_id", 0).execute()

        # 4. Xóa file Cache local
        cache_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/identity_cache.json"))
        if os.path.exists(cache_path):
            logger.info(f"- Đang xóa file cache: {cache_path}")
            os.remove(cache_path)
            
        logger.info("✅ ĐÃ XÓA SẠCH TẤT CẢ CAMERA. Hệ thống đã sẵn sàng để reset/re-provision.")
        
    except Exception as exc:
        logger.error(f"❌ Lỗi khi xóa dữ liệu: {exc}")

if __name__ == "__main__":
    confirm = input("⚠️ BẠN CÓ CHẮC CHẮN MUỐN XÓA TẤT CẢ CAMERA? (y/n): ")
    if confirm.lower() == 'y':
        delete_all_cameras()
    else:
        logger.info("Đã hủy thao tác.")
