from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / "backend" / ".env"


def build_client(key_name: str):
    load_dotenv(ENV_PATH)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv(key_name, "").strip()
    if not url or not key:
        raise RuntimeError(f"Thiếu {key_name} hoặc SUPABASE_URL trong {ENV_PATH}")
    return create_client(url, key)


def main() -> int:
    checks = [
        (
            "cameras",
            "camera_id,camera_name,location,stream_url,tb_device_name,status",
        ),
        (
            "camera_provisioning",
            "camera_id,tb_device_name,device_name,project_name,device_model,wifi_ssid,"
            "resolution,stream_scheme,stream_host,stream_port,stream_path,"
            "stream_snapshot_path,ip_address,last_seen_at,last_boot_at,online,"
            "extra_attributes",
        ),
        (
            "view_camera_summary",
            "camera_id,camera_name,configured_camera_name,configured_stream_url,"
            "device_name,project_name,device_model,wifi_ssid,resolution,stream_scheme,"
            "stream_host,stream_port,stream_path,stream_snapshot_path,ip_address,"
            "fw_version,mac_address,last_seen_at,last_boot_at,online",
        ),
    ]

    for key_name in ("SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
        print(f"[{key_name}]")
        try:
            client = build_client(key_name)
        except Exception as exc:
            print(f"  Không tạo được client: {exc}")
            continue

        for table, columns in checks:
            try:
                result = client.table(table).select(columns).limit(1).execute()
                print(f"  {table}: OK rows={len(result.data or [])}")
            except Exception as exc:
                print(f"  {table}: ERROR {exc}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
