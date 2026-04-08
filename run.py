"""
Entry point — run the TrafficCam API server.

Usage:
    python run.py                  # defaults: 0.0.0.0:8000
    python run.py --host 127.0.0.1 --port 9000
"""
import argparse
import uvicorn

from api.config import settings


def main():
    parser = argparse.ArgumentParser(description="TrafficCam ALPR API Server")
    parser.add_argument("--host", type=str, default=settings.host, help="Bind address")
    parser.add_argument("--port", type=int, default=settings.port, help="Server port")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")
    args = parser.parse_args()

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
