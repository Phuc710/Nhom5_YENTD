import sqlite3
import threading
import time
from typing import Callable


PHASE_META = {
    "GREEN": {"phase": "XANH", "camera": "IDLE"},
    "YELLOW": {"phase": "VÀNG", "camera": "WARMUP"},
    "RED": {"phase": "ĐỎ", "camera": "ACTIVE"},
    "ALL_RED": {"phase": "TẤT CẢ ĐỎ", "camera": "ACTIVE"},
}


class TrafficController:
    def __init__(self, db_path: str, intersection_id: str = "tl_01"):
        self.db_path = db_path
        self.intersection_id = intersection_id
        self.lock = threading.RLock()
        self.runtime = {}
        self.profile = {}
        self._load_runtime()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_profile(self, conn: sqlite3.Connection):
        row = conn.execute(
            """
            SELECT id, name, green_ms, yellow_ms, red_ms, all_red_ms
            FROM traffic_light_profiles
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if row:
            return dict(row)

        conn.execute(
            """
            INSERT INTO traffic_light_profiles (name, green_ms, yellow_ms, red_ms, all_red_ms)
            VALUES ('Mặc định', 30000, 5000, 30000, 1000)
            """
        )
        conn.commit()
        return self._ensure_profile(conn)

    def _load_runtime(self):
        with self.lock:
            conn = self._connect()
            try:
                self.profile = self._ensure_profile(conn)
                row = conn.execute(
                    """
                    SELECT intersection_id, mode, current_state, state_started_at,
                           state_duration_ms, profile_id, manual_source, updated_at
                    FROM traffic_light_runtime
                    WHERE intersection_id = ?
                    """,
                    (self.intersection_id,),
                ).fetchone()
                if row:
                    self.runtime = dict(row)
                else:
                    now_ms = int(time.time() * 1000)
                    self.runtime = {
                        "intersection_id": self.intersection_id,
                        "mode": "AUTO",
                        "current_state": "RED",
                        "state_started_at": now_ms,
                        "state_duration_ms": int(self.profile["red_ms"]),
                        "profile_id": self.profile["id"],
                        "manual_source": "",
                        "updated_at": int(time.time()),
                    }
                    self._persist_runtime(conn)
            finally:
                conn.close()

    def _persist_runtime(self, conn: sqlite3.Connection | None = None):
        owns_conn = conn is None
        conn = conn or self._connect()
        try:
            conn.execute(
                """
                INSERT INTO traffic_light_runtime (
                    intersection_id, mode, current_state, state_started_at,
                    state_duration_ms, profile_id, manual_source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(intersection_id) DO UPDATE SET
                    mode = excluded.mode,
                    current_state = excluded.current_state,
                    state_started_at = excluded.state_started_at,
                    state_duration_ms = excluded.state_duration_ms,
                    profile_id = excluded.profile_id,
                    manual_source = excluded.manual_source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    self.runtime["intersection_id"],
                    self.runtime["mode"],
                    self.runtime["current_state"],
                    self.runtime["state_started_at"],
                    self.runtime["state_duration_ms"],
                    self.runtime.get("profile_id"),
                    self.runtime.get("manual_source") or "",
                ),
            )
            conn.commit()
        finally:
            if owns_conn:
                conn.close()

    def _log_event(self, state: str, source: str):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO traffic_light_events (
                    intersection_id, mode, state, started_at, duration_ms, event_source
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.intersection_id,
                    self.runtime["mode"],
                    state,
                    self.runtime["state_started_at"],
                    self.runtime["state_duration_ms"],
                    source,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _state_duration_ms(self, state: str) -> int:
        state = (state or "RED").upper()
        if state == "GREEN":
            return int(self.profile["green_ms"])
        if state == "YELLOW":
            return int(self.profile["yellow_ms"])
        if state == "ALL_RED":
            return int(self.profile.get("all_red_ms") or 1000)
        return int(self.profile["red_ms"])

    def _next_auto_state(self, state: str) -> str:
        order = {"GREEN": "YELLOW", "YELLOW": "RED", "RED": "GREEN", "ALL_RED": "GREEN"}
        return order.get((state or "RED").upper(), "RED")

    def get_runtime(self) -> dict:
        with self.lock:
            current_state = self.runtime["current_state"]
            meta = PHASE_META.get(current_state, PHASE_META["RED"])
            now_ms = int(time.time() * 1000)
            remaining_ms = max(0, int(self.runtime["state_duration_ms"]) - (now_ms - int(self.runtime["state_started_at"])))
            return {
                "intersection_id": self.runtime["intersection_id"],
                "device_id": self.intersection_id,
                "mode": self.runtime["mode"],
                "current_state": current_state,
                "light": current_state,
                "phase": meta["phase"],
                "camera": meta["camera"],
                "state_started_at": int(self.runtime["state_started_at"]),
                "state_duration_ms": int(self.runtime["state_duration_ms"]),
                "remaining_ms": remaining_ms,
                "profile_id": self.runtime.get("profile_id"),
                "manual_source": self.runtime.get("manual_source") or "",
                "cycle_profile": {
                    "green_ms": int(self.profile["green_ms"]),
                    "yellow_ms": int(self.profile["yellow_ms"]),
                    "red_ms": int(self.profile["red_ms"]),
                    "all_red_ms": int(self.profile.get("all_red_ms") or 1000),
                },
                "updated_at": int(time.time()),
            }

    def set_mode(self, mode: str, manual_source: str = "") -> dict:
        mode = (mode or "AUTO").upper()
        if mode not in {"AUTO", "MANUAL", "EMERGENCY"}:
            mode = "AUTO"
        with self.lock:
            self.runtime["mode"] = mode
            self.runtime["manual_source"] = manual_source or ""
            self._persist_runtime()
            return self.get_runtime()

    def apply_profile(self, profile_id: int | None = None, *, name: str | None = None,
                      green_ms: int | None = None, yellow_ms: int | None = None,
                      red_ms: int | None = None, all_red_ms: int | None = None) -> dict:
        with self.lock:
            conn = self._connect()
            try:
                if profile_id:
                    row = conn.execute(
                        "SELECT id, name, green_ms, yellow_ms, red_ms, all_red_ms FROM traffic_light_profiles WHERE id = ?",
                        (profile_id,),
                    ).fetchone()
                else:
                    row = None

                if row:
                    self.profile = dict(row)
                else:
                    profile_name = name or "Tùy chỉnh"
                    existing = conn.execute(
                        "SELECT id FROM traffic_light_profiles WHERE name = ?",
                        (profile_name,),
                    ).fetchone()
                    if existing:
                        conn.execute(
                            """
                            UPDATE traffic_light_profiles
                            SET green_ms=?, yellow_ms=?, red_ms=?, all_red_ms=?, updated_at=CURRENT_TIMESTAMP
                            WHERE id=?
                            """,
                            (
                                max(5000, int(green_ms or self.profile["green_ms"])),
                                max(2000, int(yellow_ms or self.profile["yellow_ms"])),
                                max(5000, int(red_ms or self.profile["red_ms"])),
                                max(0, int(all_red_ms if all_red_ms is not None else self.profile.get("all_red_ms") or 1000)),
                                existing["id"],
                            ),
                        )
                        conn.commit()
                        row = conn.execute(
                            "SELECT id, name, green_ms, yellow_ms, red_ms, all_red_ms FROM traffic_light_profiles WHERE id = ?",
                            (existing["id"],),
                        ).fetchone()
                    else:
                        conn.execute(
                            """
                            INSERT INTO traffic_light_profiles (name, green_ms, yellow_ms, red_ms, all_red_ms)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                profile_name,
                                max(5000, int(green_ms or self.profile["green_ms"])),
                                max(2000, int(yellow_ms or self.profile["yellow_ms"])),
                                max(5000, int(red_ms or self.profile["red_ms"])),
                                max(0, int(all_red_ms if all_red_ms is not None else self.profile.get("all_red_ms") or 1000)),
                            ),
                        )
                        conn.commit()
                        row = conn.execute(
                            "SELECT id, name, green_ms, yellow_ms, red_ms, all_red_ms FROM traffic_light_profiles ORDER BY id DESC LIMIT 1"
                        ).fetchone()
                    self.profile = dict(row)

                self.runtime["profile_id"] = self.profile["id"]
                if self.runtime["mode"] == "AUTO":
                    self.runtime["state_duration_ms"] = self._state_duration_ms(self.runtime["current_state"])
                self._persist_runtime(conn)
                return self.get_runtime()
            finally:
                conn.close()

    def force_state(self, state: str, source: str = "MANUAL") -> dict:
        state = (state or "RED").upper()
        if state not in {"GREEN", "YELLOW", "RED", "ALL_RED"}:
            state = "RED"
        with self.lock:
            self.runtime["mode"] = "MANUAL" if source != "EMERGENCY" else "EMERGENCY"
            self.runtime["current_state"] = state
            self.runtime["state_started_at"] = int(time.time() * 1000)
            self.runtime["state_duration_ms"] = self._state_duration_ms(state)
            self.runtime["manual_source"] = source
            self._persist_runtime()
            self._log_event(state, source)
            return self.get_runtime()

    def restore_auto(self) -> dict:
        with self.lock:
            self.runtime["mode"] = "AUTO"
            self.runtime["manual_source"] = ""
            self.runtime["state_started_at"] = int(time.time() * 1000)
            self.runtime["state_duration_ms"] = self._state_duration_ms(self.runtime["current_state"])
            self._persist_runtime()
            self._log_event(self.runtime["current_state"], "AUTO")
            return self.get_runtime()

    def tick(self) -> bool:
        with self.lock:
            if self.runtime["mode"] != "AUTO":
                return False
            now_ms = int(time.time() * 1000)
            elapsed = now_ms - int(self.runtime["state_started_at"])
            if elapsed < int(self.runtime["state_duration_ms"]):
                return False
            next_state = self._next_auto_state(self.runtime["current_state"])
            self.runtime["current_state"] = next_state
            self.runtime["state_started_at"] = now_ms
            self.runtime["state_duration_ms"] = self._state_duration_ms(next_state)
            self.runtime["manual_source"] = ""
            self._persist_runtime()
            self._log_event(next_state, "AUTO")
            return True


def phase_camera(light: str) -> str:
    return PHASE_META.get((light or "RED").upper(), PHASE_META["RED"])["camera"]


def phase_label(light: str) -> str:
    return PHASE_META.get((light or "RED").upper(), PHASE_META["RED"])["phase"]


def is_enforcement_active(light: str) -> bool:
    return (light or "RED").upper() in {"RED", "ALL_RED"}
