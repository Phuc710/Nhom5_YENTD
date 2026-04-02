"""Điểm vào FastAPI của backend giám sát vi phạm giao thông."""

import asyncio
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


def configure_asyncio_policy() -> None:
    """Áp dụng event loop phù hợp cho Windows trước khi import các service async."""
    if sys.platform.startswith("win"):
        # SelectorEventLoop là bắt buộc cho aiomqtt (paho-mqtt) trên Windows
        # vì nó hỗ trợ add_reader/add_writer (ProactorLoop thì không).
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


configure_asyncio_policy()

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.api.cameras import router as cameras_router
from backend.api.dashboard import router as dashboard_router
from backend.api.realtime import router as realtime_router
from backend.api.streams import router as streams_router
from backend.api.violations import router as violations_router
from backend.api.settings import router as settings_router
from backend.config.settings import get_settings
from backend.database.supabase_client import init_supabase
from backend.repositories.camera_repository import CameraRepository
from backend.services.camera_service import CameraService
from backend.services.realtime_service import realtime_service
from backend.services.supabase_realtime_service import supabase_realtime_service
from backend.services.stream_manager import stream_manager
from backend.services.mqtt_consumer import mqtt_consumer
from backend.utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)
API_VERSION = "1.0.0"
STARTUP_SEPARATOR = "=" * 60
PORT_PROBE_TIMEOUT_SECONDS = 1.5


def ensure_upload_directories() -> None:
    """Tạo các thư mục upload cần thiết nếu chưa tồn tại."""
    os.makedirs(f"{settings.upload_dir}/violations", exist_ok=True)
    os.makedirs(f"{settings.upload_dir}/plates", exist_ok=True)


def log_startup_banner() -> None:
    """Ghi log banner khởi động ngắn gọn, nhất quán."""
    logger.info(STARTUP_SEPARATOR)
    logger.info("HỆ THỐNG GIÁM SÁT VI PHẠM GIAO THÔNG")
    logger.info(STARTUP_SEPARATOR)


def log_runtime_configuration() -> None:
    """Ghi lại các thông số runtime theo nhóm chuyên biệt dùng icon."""
    # Nhóm Network
    logger.info("🌐 [MẠNG] Host: %s | Port: %s", settings.host, settings.port)
    logger.info("🌐 [MẠNG] IP LAN: %s | CORS: %d origins", settings.local_lan_ip, len(settings.cors_origins_list))
    
    # Nhóm Database & MQTT
    logger.info("📡 [DB] Supabase: ✅ Sẵn sàng (%s)", settings.supabase_auth_mode)
    logger.info("📡 [MQTT] Mosquitto: ✅ %s:%d", settings.mqtt_host, settings.mqtt_port)
    
    # Nhóm Lưu trữ & AI
    logger.info("💾 [LƯU TRỮ] Upload: %s/ | Bucket: %s", settings.upload_dir, settings.supabase_storage_bucket)
    logger.info("🧠 [MÔ HÌNH AI] Preload: %s | Mode: yolov5_nano", 
                "✅ BẬT" if settings.ml_preload_on_startup else "⚪ TẮT")
    
    # Nhóm Workers
    logger.info("⚙️  [TIẾN TRÌNH] TTL: %ds | Tự chạy: %s", 
                settings.camera_status_ttl_seconds, 
                "✅ BẬT" if settings.stream_workers_start_on_startup else "⏸️  CHỜ")


def build_public_api_url() -> str:
    """Suy ra URL public để hiển thị trong log."""
    return (settings.public_api_url or f"http://localhost:{settings.port}").rstrip("/")


def resolve_probe_host(host: str) -> str:
    """Chọn host cục bộ phù hợp để kiểm tra một backend đã chạy sẵn hay chưa."""
    if host in {"0.0.0.0", "::", ""}:
        return "127.0.0.1"
    return host


def is_port_available(host: str, port: int) -> bool:
    """Trả về True nếu host:port còn trống để bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def is_backend_already_running(host: str, port: int) -> bool:
    """Kiểm tra xem cổng bận có phải do backend này đang chạy sẵn hay không."""
    probe_host = resolve_probe_host(host)
    health_url = f"http://{probe_host}:{port}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=PORT_PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "healthy"
    except (OSError, ValueError, urllib.error.URLError, TimeoutError):
        return False


def check_startup_preconditions() -> tuple[bool, int]:
    """Kiểm tra điều kiện khởi động và cho biết có nên chạy server hay không."""
    if is_port_available(settings.host, settings.port):
        return True, 0

    probe_host = resolve_probe_host(settings.host)
    if is_backend_already_running(settings.host, settings.port):
        logger.warning(
            "Backend đã chạy sẵn tại http://%s:%s . Bỏ qua lần khởi động trùng này.",
            probe_host,
            settings.port,
        )
        return False, 0

    logger.error(
        "Không thể khởi động backend vì cổng %s đang được tiến trình khác sử dụng. "
        "Hãy dừng tiến trình cũ hoặc đổi PORT trong backend/.env.",
        settings.port,
    )
    return False, 1


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Khởi tạo tài nguyên dùng chung khi app start và giải phóng khi dừng."""
    camera_service = CameraService()
    auto_sync_task: asyncio.Task | None = None
    preload_task: asyncio.Task | None = None
    last_auto_sync_error: str | None = None

    log_startup_banner()
    loop = asyncio.get_running_loop()
    logger.info("Asyncio loop type: %s", type(loop).__name__)
    realtime_service.bind_loop(asyncio.get_running_loop())
    init_supabase()
    ensure_upload_directories()
    log_runtime_configuration()

    async def preload_models_background() -> None:
        try:
            from backend.ml.detector import get_detector

            detector = await asyncio.to_thread(get_detector)
            logger.info("Đã preload mô hình AI trên %s", detector.device)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Preload mô hình AI thất bại, backend vẫn tiếp tục khởi động: %s", exc)

    if settings.ml_preload_on_startup:
        preload_task = asyncio.create_task(preload_models_background(), name="ml_preload")
        logger.info("🧠 Preload mô hình AI chạy nền sau startup")

    async def auto_sync_devices_loop() -> None:
        nonlocal last_auto_sync_error
        interval = max(5, int(settings.thingsboard_auto_sync_interval_seconds))
        while True:
            await asyncio.sleep(interval)
            try:
                summary = await camera_service.sync_devices_from_thingsboard()
                if last_auto_sync_error is not None:
                    logger.info("Tự động đồng bộ ThingsBoard đã khôi phục")
                    last_auto_sync_error = None
                if summary["scanned"]:
                    logger.info(
                        "Tự động đồng bộ ThingsBoard | đã quét=%s | đã tạo=%s | đã cập nhật=%s",
                        summary["scanned"],
                        summary["created"],
                        summary["updated"],
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                if error_text != last_auto_sync_error:
                    logger.warning("Tự động đồng bộ ThingsBoard không sẵn dụng: %s", error_text)
                    last_auto_sync_error = error_text

    if settings.thingsboard_auto_sync_on_startup:
        try:
            summary = await camera_service.sync_devices_from_thingsboard()
            logger.info(
                "🤝 Tự động đồng bộ thiết bị khi khởi động | đã quét=%s | đã tạo=%s | đã cập nhật=%s",
                summary["scanned"],
                summary["created"],
                summary["updated"],
            )
        except Exception as exc:
            logger.warning("Tự động đồng bộ ThingsBoard khi khởi động không khả dụng: %s", exc)

    # Nạp Identity Cache (MAC → camera_id) để heartbeat siêu nhanh
    try:
        camera_service.warm_identity_cache()
    except Exception as exc:
        logger.warning("⚠️ Warm identity cache thất bại: %s", exc)

    # Bắt đầu lắng nghe Supabase Realtime
    supabase_realtime_service.on_camera_change(camera_service.on_camera_db_changed)
    await supabase_realtime_service.start()

    # Khởi động Stream Workers cho tất cả camera nếu được bật
    if settings.enable_stream_workers and settings.stream_workers_start_on_startup:
        try:
            await stream_manager.start_all()
        except Exception as exc:
            logger.warning("⚠️ Không thể khởi động StreamManager: %s", exc)
    elif settings.enable_stream_workers:
        logger.warning("⏸️ Stream workers sẽ chờ camera provision/heartbeat rồi tự bật")
    else:
        logger.warning("⏸️ Stream workers đang tắt bằng ENABLE_STREAM_WORKERS=false")

    # Khởi động MQTT Consumer (subscribe Mosquitto, nhận telemetry realtime từ ESP32)
    if mqtt_consumer.is_configured():
        await mqtt_consumer.start()
    else:
        logger.warning("⚠️ MQTT_HOST chưa cấu hình — light_state phụ thuộc vào HTTP heartbeat")

    if settings.thingsboard_auto_sync_interval_seconds > 0:
        auto_sync_task = asyncio.create_task(auto_sync_devices_loop(), name="thingsboard_auto_sync")

    logger.info("Tài liệu API: %s/docs", build_public_api_url())
    logger.info(STARTUP_SEPARATOR)

    yield

    logger.info("Đang dừng StreamManager...")
    if auto_sync_task:
        auto_sync_task.cancel()
        try:
            await auto_sync_task
        except asyncio.CancelledError:
            pass
    if preload_task and not preload_task.done():
        preload_task.cancel()
        try:
            await preload_task
        except asyncio.CancelledError:
            pass
    await supabase_realtime_service.stop()
    await mqtt_consumer.stop()
    if settings.enable_stream_workers:
        await stream_manager.stop_all()
    await camera_service.close()
    logger.info("Backend đã dừng hoàn toàn")



app = FastAPI(
    title="API Giám sát vi phạm giao thông",
    description="Backend xử lý camera ESP32-S3, ThingsBoard và hồ sơ vi phạm giao thông",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "Unknown"
    
    # Bỏ qua log cho các endpoint không quan trọng hoặc quá nhiều
    noisy_prefixes = (
        "/api/ws/stream",
        "/api/realtime/stream",
        "/uploads/",
    )
    noisy_suffixes = ("/stream", "/live-view/sse")
    noisy_get_patterns = (
        r"^/health$",
        r"^/api/cameras$",
        r"^/api/cameras/\d+$",
        r"^/api/cameras/\d+/zones$",
        r"^/api/violations/recent$",
    )

    if (
        request.method == "OPTIONS"
        or request.url.path.startswith(noisy_prefixes)
        or request.url.path.endswith(noisy_suffixes)
        or (request.method == "GET" and any(re.match(pattern, request.url.path) for pattern in noisy_get_patterns))
    ):
        return await call_next(request)
        
    logger.info(f"🚀 YÊU CẦU ĐẾN | {request.method: <6} | {request.url.path} | IP: {client_ip}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        status_code = response.status_code
        if status_code < 400:
            logger.info(f"✅ PHẢN HỒI ĐI | {request.method: <6} | {request.url.path} | HTTP {status_code} | {process_time:.2f}ms")
        else:
            logger.error(f"❌ LỖI XỬ LÝ  | {request.method: <6} | {request.url.path} | HTTP {status_code} | {process_time:.2f}ms")
            
        return response
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.exception(f"💥 LỖI HỆ THỐNG | {request.method: <6} | {request.url.path} | LỖI HỆ THỐNG | {process_time:.2f}ms")
        raise


app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Centralized API Router
api_router = APIRouter(prefix="/api")
api_router.include_router(cameras_router)
api_router.include_router(violations_router)
api_router.include_router(dashboard_router)
api_router.include_router(realtime_router)
api_router.include_router(streams_router)
api_router.include_router(settings_router)

app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"❌ LỖI XỬ LÝ  | {request.method: <6} | {request.url.path} | HTTP 422 | ValidationError: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "API Giám sát vi phạm giao thông",
        "version": API_VERSION,
        "status": "online",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health", tags=["System"])
async def health():
    audit = stream_manager.audit_cameras()
    repo = CameraRepository()
    cameras = repo.get_all()
    workers = stream_manager.status().get("workers") or []
    worker_map = {
        int(worker["camera_id"]): worker
        for worker in workers
        if worker.get("camera_id") is not None
    }
    devices_by_mac = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        if camera_id is None:
            continue
        worker = worker_map.get(int(camera_id), {})
        devices_by_mac.append(
            {
                "mac_address": camera.get("mac_address") or "unknown",
                "camera_name": camera.get("camera_name") or camera.get("device_name") or camera.get("tb_device_name"),
                "ip_address": camera.get("ip_address"),
                "stream_url": camera.get("stream_url"),
                "online": bool(camera.get("online")),
                "stream_running": bool(worker.get("running")),
                "stream_connected": bool(worker.get("connected")),
                "last_seen_at": camera.get("last_seen_at"),
                "last_boot_at": camera.get("last_boot_at"),
            }
        )
    devices_by_mac.sort(key=lambda item: str(item.get("mac_address") or ""))

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "supabase_auth_mode": settings.supabase_auth_mode,
        "cors_origins": settings.cors_origins_list,
        "public_api_url": settings.public_api_url or None,
        "camera_audit": {
            "total": audit["total"],
            "ready": len(audit["ready"]),
            "skipped": len(audit["skipped"]),
        },
        "devices_by_mac": devices_by_mac,
    }


def build_server_config() -> uvicorn.Config:
    """Tạo cấu hình Uvicorn từ settings hiện tại."""
    backend_dir = str(Path(__file__).resolve().parent)
    return uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.hot_reload,
        loop="asyncio",
        reload_dirs=[backend_dir] if settings.hot_reload else None,
        reload_excludes=["logs/*", "backend/uploads/*", ".pio/*", "frontend/*", "database/*", "detected_plates/*"] if settings.hot_reload else None,
        log_level=settings.log_level.lower(),
    )


async def serve() -> None:
    """Khởi động Uvicorn server."""
    server = uvicorn.Server(build_server_config())
    await server.serve()


def main() -> int:
    """Điểm vào CLI của backend."""
    configure_asyncio_policy()
    should_start_server, exit_code = check_startup_preconditions()
    if not should_start_server:
        return exit_code

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Nhận tín hiệu dừng từ bàn phím.")
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code != 0:
            logger.error("Backend dừng trong lúc khởi động với mã %s.", code)
        return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
