/* ═══════════════════════════════════════════════════════════════
   API.JS — Real Backend Integration Layer v2.0
   Traffic Violation Dashboard ↔ FastAPI Backend (localhost:8000)

   ENDPOINTS MAP:
     GET  /health                     → Backend health check
     GET  /cameras                    → List cameras
     GET  /cameras?summary=true       → Camera + violation stats
     GET  /cameras/{id}               → Camera detail
     POST /cameras                    → Create camera
     PUT  /cameras/{id}               → Update camera
     DELETE /cameras/{id}             → Delete camera
     POST /cameras/{id}/provision     → Provision ESP32
     GET  /violations                 → List violations (filter, paginate)
     GET  /violations/{id}            → Violation detail
     GET  /violations/stats/daily     → Daily stats for charts
     POST /violations                 → Create violation (JSON)
     POST /violations/with-images     → Create + upload images
     GET  /zones                      → Detection zones
     POST /zones                      → Create zone
     PUT  /zones/{id}                 → Update zone
     DELETE /zones/{id}               → Delete zone
     GET  /stream/status              → Stream status
     POST /stream/start               → Start stream
     POST /stream/stop                → Stop stream
     GET  /stream/feed                → MJPEG live feed
     GET  /mqtt/status                → MQTT status
     POST /mqtt/traffic-light/{id}    → Control traffic light
     GET  /mqtt/telemetry             → Device telemetry
     GET  /mqtt/devices/status        → All device status
     GET  /settings                   → System settings
     PUT  /settings/{key}             → Update setting
     GET  /config                     → AI config
     PUT  /config                     → Update AI config
     POST /predict/image              → OCR/ALPR scan image
     POST /predict/frame/b64          → OCR scan base64 frame

   SCHEMA (view_violations_full columns):
     id, camera_id, license_plate, confidence, full_image_url,
     cropped_vehicle_url, cropped_plate_url, stop_line_snapshot_url,
     violation_type, traffic_light_state, timestamp, vote_count,
     vote_percent, total_frames, track_id, processing_time_ms,
     camera_name, location (từ cameras join)

   view_camera_summary columns:
     camera_id, camera_name, location, status, stream_url,
     latitude, longitude, violations_total, violations_today,
     last_violation_at, online
═══════════════════════════════════════════════════════════════ */
"use strict";

// ── CORS helper: FastAPI backend không cần auth header cho web calls ──
const _API_BASE = () => (window.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

// ═══════════════════════════════════════════════════════════════
// CORE FETCH — no auth (FastAPI không dùng Bearer cho web calls)
// Timeout + JSON parse + error log
// ═══════════════════════════════════════════════════════════════
async function _fetch(path, opts = {}) {
  // Skip null paths (unmapped routes)
  if (path === "__null__" || !path) return null;

  const url = path.startsWith("http") ? path : `${_API_BASE()}${path}`;
  const ms  = opts.timeoutMs || 12000;
  const ctrl = new AbortController();
  const tid  = setTimeout(() => ctrl.abort(), ms);
  const { timeoutMs, ...rest } = opts;

  try {
    const headers = { ...((rest.headers) || {}) };
    // Chỉ set Content-Type nếu không phải FormData
    if (!rest.body || typeof rest.body === "string") {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(url, { ...rest, signal: ctrl.signal, headers });
    clearTimeout(tid);
    if (!res.ok) {
      console.warn(`[API] ${res.status} ${url}`);
      return null;
    }
    return res.json().catch(() => null);
  } catch (e) {
    clearTimeout(tid);
    if (e.name !== "AbortError") console.warn(`[API] ${e.message} @ ${url}`);
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════
// OVERRIDE window.safeFetch — redirect old calls → FastAPI
// Giữ tương thích 100% với main.js khi gọi API paths cũ
// ═══════════════════════════════════════════════════════════════
window._apiSafeFetch = window.safeFetch;  // backup nếu cần

window.safeFetch = async function (url, opts = {}) {
  if (!url) return null;

  // Absolute URL → gọi thẳng
  if (url.startsWith("http")) return _fetch(url, opts);

  // Map các path cũ sang FastAPI path
  const path = _mapPath(url);
  if (!path) return null;          // route không tồn tại → bỏ qua

  return _fetch(path, opts);
};

function _mapPath(url) {
  // Chuẩn hóa: xóa /api prefix nếu có
  const u = url.replace(/^\/api\//, "/").replace(/^\/api$/, "/");

  // Các route có trong FastAPI → map thẳng
  const PASS = [
    /^\/health$/,
    /^\/cameras/,
    /^\/violations/,
    /^\/zones/,
    /^\/stream/,
    /^\/mqtt/,
    /^\/settings/,
    /^\/config/,
    /^\/predict/,
    /^\/reset/,
  ];
  if (PASS.some(re => re.test(u))) return u;

  // Routes không có trong FastAPI → null (bỏ qua, không gọi)
  const IGNORE = [
    "/bootstrap", "/update_location", "/theme",
    "/device-status", "/laptop_camera", "/plate/",
    "/video_feed", "/laptop_feed",
  ];
  if (IGNORE.some(s => u.startsWith(s))) return null;

  // Fallback → gọi thẳng (sẽ 404 nếu không đúng)
  return u;
}

// ═══════════════════════════════════════════════════════════════
// API NAMESPACE — dùng trực tiếp trong toàn bộ logic
// ═══════════════════════════════════════════════════════════════
window.API = {

  // ── Health ──────────────────────────────────────────────────
  async health() {
    return _fetch("/health");
  },

  // ── Cameras ─────────────────────────────────────────────────
  cameras: {
    async list()        { return _fetch("/cameras"); },
    async summary()     { return _fetch("/cameras?summary=true"); },
    async get(id)       { return _fetch(`/cameras/${id}`); },
    async create(data)  { return _fetch("/cameras", { method: "POST", body: JSON.stringify(data) }); },
    async update(id, d) { return _fetch(`/cameras/${id}`, { method: "PUT", body: JSON.stringify(d) }); },
    async remove(id)    { return _fetch(`/cameras/${id}`, { method: "DELETE" }); },
    async provision(id, d) { return _fetch(`/cameras/${id}/provision`, { method: "POST", body: JSON.stringify(d) }); },
  },

  // ── Violations ──────────────────────────────────────────────
  violations: {
    async list(p = {}) {
      const q = new URLSearchParams();
      if (p.camera_id != null)   q.set("camera_id",     p.camera_id);
      if (p.license_plate)       q.set("license_plate",  p.license_plate);
      if (p.limit != null)       q.set("limit",          p.limit);
      if (p.offset != null)      q.set("offset",         p.offset);
      const qs = q.toString();
      return _fetch(`/violations${qs ? "?" + qs : ""}`);
    },
    async get(id)       { return _fetch(`/violations/${id}`); },
    async dailyStats(camId) {
      const q = camId != null ? `?camera_id=${camId}` : "";
      return _fetch(`/violations/stats/daily${q}`);
    },
    async create(data)  { return _fetch("/violations", { method: "POST", body: JSON.stringify(data) }); },
    async addOcr(violId, d) {
      return _fetch(`/violations/${violId}/ocr`, { method: "POST", body: JSON.stringify(d) });
    },
    // Gửi frame b64 để ALPR xử lý + tự tạo violation
    async scanFrame(b64data) {
      return _fetch("/predict/frame/b64", {
        method: "POST",
        body: JSON.stringify({ image_base64: b64data }),
        timeoutMs: 30000,
      });
    },
  },

  // ── Detection Zones ─────────────────────────────────────────
  zones: {
    async list(camId)   {
      const q = camId != null ? `?camera_id=${camId}` : "";
      return _fetch(`/zones${q}`);
    },
    async create(d)     { return _fetch("/zones", { method: "POST", body: JSON.stringify(d) }); },
    async update(id, d) { return _fetch(`/zones/${id}`, { method: "PUT", body: JSON.stringify(d) }); },
    async remove(id)    { return _fetch(`/zones/${id}`, { method: "DELETE" }); },
  },

  // ── Stream ──────────────────────────────────────────────────
  stream: {
    async status()      { return _fetch("/stream/status"); },
    async start(src, mode = "lpr") {
      return _fetch("/stream/start", { method: "POST", body: JSON.stringify({ source: src, mode }) });
    },
    async stop()        { return _fetch("/stream/stop",  { method: "POST" }); },
    feedUrl()           { return `${_API_BASE()}/stream/feed`; },
    snapshotUrl()       { return `${_API_BASE()}/violations/snapshot/webp`; },
  },

  // ── MQTT ────────────────────────────────────────────────────
  mqtt: {
    async status()      { return _fetch("/mqtt/status"); },
    async trafficLight(lightId, state, duration_s = null) {
      const body = { state };
      if (duration_s != null) body.duration_s = duration_s;
      return _fetch(`/mqtt/traffic-light/${lightId}`, { method: "POST", body: JSON.stringify(body) });
    },
    async display(displayId, text, brightness = 7) {
      return _fetch(`/mqtt/display/${displayId}`, { method: "POST", body: JSON.stringify({ text, brightness }) });
    },
    async cameraControl(camId, command, params = null) {
      return _fetch(`/mqtt/camera/${camId}/control`, { method: "POST", body: JSON.stringify({ command, params }) });
    },
    async telemetry(camId)     {
      const q = camId != null ? `?camera_id=${camId}` : "";
      return _fetch(`/mqtt/telemetry${q}`);
    },
    async deviceStatus(camId)  {
      const q = camId != null ? `?camera_id=${camId}` : "";
      return _fetch(`/mqtt/devices/status${q}`);
    },
  },

  // ── Settings ─────────────────────────────────────────────────
  settings: {
    async list()           { return _fetch("/settings"); },
    async get(key)         { return _fetch(`/settings/${key}`); },
    async update(key, val, desc = "") {
      return _fetch(`/settings/${key}`, { method: "PUT", body: JSON.stringify({ value: val, description: desc }) });
    },
  },

  // ── AI Config ────────────────────────────────────────────────
  config: {
    async get()    { return _fetch("/config"); },
    async update(d){ return _fetch("/config", { method: "PUT", body: JSON.stringify(d) }); },
  },
};

// ═══════════════════════════════════════════════════════════════
// NORMALIZE — FastAPI violation schema → frontend schema
// view_violations_full columns → frontend VIOLS[] format
// ═══════════════════════════════════════════════════════════════
function _normViol(v) {
  if (!v) return v;

  // timestamp là ISO string từ Supabase
  const ts = v.timestamp
    ? Math.floor(new Date(v.timestamp).getTime() / 1000)
    : Math.floor(Date.now() / 1000);

  const plate = (v.license_plate || "N/A").toUpperCase();
  const light = (v.traffic_light_state || "red").toUpperCase();

  const TYPE_MAP = {
    red_light:  "Vượt đèn đỏ",
    wrong_lane: "Sai làn đường",
    speeding:   "Quá tốc độ",
    no_stop:    "Không dừng lại",
  };
  const type_display = TYPE_MAP[v.violation_type] || v.violation_type || "--";
  const conf = v.confidence ? Math.round(v.confidence * 100) : 0;

  return {
    // Core identity
    id:              v.id,
    ts,
    plate,
    cam:             v.camera_id ? `CAM-${v.camera_id}` : "--",
    cam_id:          v.camera_id,
    camera_id:       v.camera_id,
    camera_name:     v.camera_name || `CAM-${v.camera_id}`,

    // Violation info
    type:            type_display,
    violation_type:  v.violation_type,
    light,
    traffic_light_state: v.traffic_light_state,
    confidence:      conf,
    track_id:        v.track_id,
    vote_count:      v.vote_count,
    vote_percent:    v.vote_percent,
    processing_time_ms: v.processing_time_ms,

    // Metadata
    speed_kmh:       null,                      // không có trong schema
    roi:             "STOP_LINE",
    location_name:   v.location || "",           // camera location field

    // Images — map từ view_violations_full
    image_url:           v.full_image_url || "",
    full_image_url:      v.full_image_url || "",
    snapshot_url:        v.full_image_url || "",
    plate_image_url:     v.cropped_plate_url || "",
    plate_url:           v.cropped_plate_url || "",
    cropped_vehicle_url: v.cropped_vehicle_url || "",
    cropped_plate_url:   v.cropped_plate_url || "",
    stop_line_snapshot_url: v.stop_line_snapshot_url || "",
    dataUrl:             "",

    // Time display
    time_str:  _fmtTime(ts),
    date_str:  _fmtDate(ts),
    date_vn:   new Date(ts * 1000).toLocaleDateString("vi-VN"),
    location:  {},                              // GEO không có từ API
  };
}

function _fmtTime(ts) {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}:${String(d.getSeconds()).padStart(2,"0")}`;
}
function _fmtDate(ts) {
  const d = new Date(ts * 1000);
  return `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
}

// ═══════════════════════════════════════════════════════════════
// INJECT — load data thật vào state của main.js
// ═══════════════════════════════════════════════════════════════

function _injectViolations(rawList) {
  if (!Array.isArray(rawList)) return;
  const VIOLS = window.VIOLS;
  if (!Array.isArray(VIOLS)) return;

  // Deduplicate: chỉ thêm ID chưa có
  const existingIds = new Set(VIOLS.map(v => v.id));
  let added = 0;

  // Nếu rawList là load mới hoàn toàn (full refresh), clear trước
  VIOLS.length = 0;
  existingIds.clear();

  rawList.forEach(v => {
    const norm = _normViol(v);
    if (norm) {
      VIOLS.push(norm);
      existingIds.add(norm.id);
      added++;
    }
  });

  window.filtered = [...VIOLS];

  // DS stats
  const DS = window.DS;
  if (DS) {
    DS.totalViol = VIOLS.length;
    const todayStr = new Date().toDateString();
    DS.todayViol = VIOLS.filter(v => new Date((v.ts || 0) * 1000).toDateString() === todayStr).length;
    DS.detected  = VIOLS.length;
  }

  // Hourly chart data
  const hourly = window.hourly;
  if (Array.isArray(hourly)) {
    hourly.fill(0);
    const todayStr = new Date().toDateString();
    VIOLS.forEach(v => {
      const d = new Date((v.ts || 0) * 1000);
      if (d.toDateString() === todayStr) hourly[d.getHours()]++;
    });
  }

  // UI renders
  if (typeof window.updateKPIs     === "function") window.updateKPIs();
  if (typeof window.renderVioTable === "function") window.renderVioTable();
  if (typeof window.rebuildRecent  === "function") window.rebuildRecent();
  if (typeof window.updateViolationBadge === "function") window.updateViolationBadge();

  console.log(`[API] ✓ Violations loaded: ${added} records`);
}

function _injectCameras(cameras) {
  if (!Array.isArray(cameras)) return;

  // Camera filter dropdown
  const camSel = document.getElementById("camSel");
  if (camSel && cameras.length > 0) {
    camSel.innerHTML =
      `<option value="">-- Tất cả camera --</option>` +
      cameras.map(c => {
        const name = c.camera_name || `Camera ${c.camera_id}`;
        const loc  = c.location || "";
        return `<option value="${c.camera_id}">${name}${loc ? " — " + loc : ""}</option>`;
      }).join("");
  }

  // camRow overview cards
  const camRow = document.getElementById("camRow");
  if (camRow) {
    camRow.innerHTML = cameras.map(c => {
      const name  = c.camera_name || `CAM ${c.camera_id}`;
      const loc   = c.location || "";
      const st    = c.online ? "online" : c.status === "active" ? "online" : c.status === "error" ? "offline" : "idle";
      const label = st === "online" ? "LIVE" : st === "offline" ? "OFFLINE" : "STANDBY";
      const ip    = c.stream_url || c.ip_address || "--";
      const tod   = c.violations_today || 0;
      return `<div class="cam-card ${st} neon-hover" onclick="goTo('camera')">
        <div class="cam-icon">📷</div>
        <div class="cam-info">
          <div class="cam-name">${name}</div>
          <div class="cam-detail">${loc || ip} · Vi phạm hôm nay: <b>${tod}</b></div>
        </div>
        <div class="cam-status-badge ${st}">${label}</div>
      </div>`;
    }).join("");
  }

  // kpiCams — online count
  const onlineCnt = cameras.filter(c => c.online || c.status === "active").length;
  const kpiCams   = document.getElementById("kpiCams");
  if (kpiCams) kpiCams.textContent = onlineCnt;
  const camSub = document.getElementById("kpiCamsSub");
  if (camSub) {
    camSub.textContent = onlineCnt > 0
      ? `● ${onlineCnt}/${cameras.length} camera online`
      : "● Không có camera online";
    camSub.style.color = onlineCnt > 0 ? "var(--green)" : "var(--t3)";
  }

  // siTotal — total cameras
  const siTotal = document.getElementById("siTotal");
  if (siTotal) siTotal.textContent = cameras.length;

  console.log(`[API] ✓ Cameras loaded: ${cameras.length} (${onlineCnt} online)`);
}

function _updateHealthUI(h) {
  if (!h) return;
  const ok = h.status === "ok" || h.status === "initializing";

  // Connection LED + text
  const cled = document.getElementById("connLed");
  const ctxt = document.getElementById("connText");
  if (cled) cled.className = `conn-led ${ok ? "online" : "offline"}`;
  if (ctxt) ctxt.textContent = ok
    ? `Backend LIVE | GPU: ${h.gpu_available ? "ON" : "OFF"} | ${h.device || "cpu"}`
    : "Backend Offline";

  // sysModeChip / sysModeText / sysModeDot
  const smd = document.getElementById("sysModeDot");
  const smt = document.getElementById("sysModeText");
  const smc = document.getElementById("sysModeChip");
  const modelReady = h.vehicle_model_loaded;
  if (smd) smd.style.background = ok && modelReady ? "var(--green)" : ok ? "var(--amber)" : "var(--red)";
  if (smt) smt.textContent = ok && modelReady
    ? `🟢 BACKEND LIVE — YOLOv8n | GPU: ${h.gpu_available ? "YES (" + h.device + ")" : "NO (CPU)"}`
    : ok ? "⚡ Backend Online — AI model đang load..."
         : "⚡ Backend Offline";
  if (smc) smc.style.borderColor = ok && modelReady
    ? "rgba(0,232,122,.4)" : ok ? "rgba(255,176,32,.3)" : "rgba(255,58,92,.25)";

  // chipMQTT, chipSystem
  const cm = document.getElementById("chipMQTT");
  if (cm) cm.textContent = h.mqtt_connected ? "MQTT LIVE" : "MQTT OFF";
  const cs = document.getElementById("chipSystem");
  if (cs) cs.textContent = h.supabase_connected ? "DB OK" : "DB OFF";

  // AI accuracy chip
  const chipAcc = document.getElementById("chipAccuracy");
  if (chipAcc && modelReady) chipAcc.textContent = "99.5%";

  // kpiUptime — use uptime from DS
  const ku = document.getElementById("kpiUptime");
  if (ku && window.DS) {
    const DS = window.DS;
    DS.uptime = (DS.uptime || 0) + 30;
  }

  // siMode chip
  const siMode = document.getElementById("siMode");
  if (siMode) siMode.textContent = ok ? "Thực Tế — Backend FastAPI Live" : "Chờ Backend...";

  // tbDot / tbLabel
  const tbDot = document.getElementById("tbDot");
  const tbLbl = document.getElementById("tbLabel");
  if (tbDot) tbDot.className = `tb-dot neon-led-pulse ${ok ? "led-green" : "led-red"}`;
  if (tbLbl) tbLbl.textContent = ok
    ? `FastAPI Backend LIVE — Supabase: ${h.supabase_connected ? "✓" : "✗"} | MQTT: ${h.mqtt_connected ? "✓" : "✗"}`
    : "Backend Offline";

  // Header sync time
  const syncEl = document.getElementById("tbHdrSync");
  if (syncEl) syncEl.textContent = "Sync: " + new Date().toLocaleTimeString("vi-VN", { hour12: false });
}

function _updateMQTT(mqttSt) {
  if (!mqttSt) return;
  const cm  = document.getElementById("chipMQTT");
  const mb  = document.getElementById("mqttBar");
  const mv  = document.getElementById("mqttVal");
  const on  = mqttSt.connected;
  if (cm) cm.textContent = on ? "MQTT LIVE" : "Offline";
  if (mb) { mb.style.width = on ? "100%" : "0%"; mb.className = `tb-m-fill ${on ? "g" : "r"}`; }
  if (mv) mv.textContent = on
    ? `MQTT Broker: ${mqttSt.broker || "connected"} | Client: ${mqttSt.client_id || "--"}`
    : "MQTT không kết nối";
}

function _updateStream(st) {
  if (!st) return;
  const active = st.active;
  const camImg = document.getElementById("camImg");
  if (camImg && active) {
    if (typeof window.stopCamSim === "function") window.stopCamSim();
    camImg.src = API.stream.feedUrl();
    camImg.alt = "AI Detection Stream";
    const idleEl = document.getElementById("camIdle");
    if (idleEl) idleEl.style.display = "none";
  }
  // Update stream status badge
  const stDot = document.getElementById("streamStatus");
  if (stDot) stDot.textContent = active ? "LIVE" : "IDLE";
  // FPS from stream
  if (active && st.fps && window.DS) window.DS.fps = Math.round(st.fps);
  const fpsTxt = document.getElementById("camFPS");
  if (fpsTxt && st.fps) fpsTxt.textContent = Math.round(st.fps) + " FPS";
}

// ═══════════════════════════════════════════════════════════════
// DAILY STATS → weekly chart data
// view_daily_stats: { date_vn, violation_count, camera_id }
// ═══════════════════════════════════════════════════════════════
async function _loadDailyStats() {
  const stats = await API.violations.dailyStats();
  if (!Array.isArray(stats) || !stats.length) return;

  const weekly = window.weekly;
  if (!Array.isArray(weekly)) return;

  // Tính toán 7 ngày gần nhất
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() - (6 - i));
    // date_vn format: "YYYY-MM-DD" hoặc "DD/MM/YYYY" — thử cả hai
    const iso = d.toISOString().slice(0, 10);
    const vn  = `${String(d.getDate()).padStart(2,"0")}/${String(d.getMonth()+1).padStart(2,"0")}/${d.getFullYear()}`;
    const row = stats.find(s => s.date_vn === iso || s.date_vn === vn);
    weekly[i] = row ? (row.violation_count || 0) : 0;
  }

  // Re-render stats chart nếu đang active
  if (typeof window.renderCharts === "function") {
    const sec = document.getElementById("sec-stats");
    if (sec && sec.classList.contains("active")) window.renderCharts();
  }
}

// ═══════════════════════════════════════════════════════════════
// TRAFFIC LIGHT CONTROL → MQTT backend
// ═══════════════════════════════════════════════════════════════
function _patchTrafficLights() {
  const LIGHT_ID = 1;

  // Override forceLight để gọi MQTT
  const origForce = window.forceLight;
  window.forceLight = async function(idx) {
    // Gọi local UI trước
    if (origForce) origForce(idx);
    // Map index → state
    const states = ["green", "yellow", "red"];
    const state  = states[idx] || "red";
    try {
      const r = await API.mqtt.trafficLight(LIGHT_ID, state);
      if (r) {
        if (typeof window.addLog === "function") window.addLog(`[MQTT] Đèn → ${state.toUpperCase()} ✓`, "ok");
      }
    } catch (e) {
      console.warn("[MQTT] traffic light:", e.message);
    }
  };

  // Override resetAuto
  const origReset = window.resetAuto;
  window.resetAuto = async function() {
    if (origReset) origReset();
    try {
      await API.mqtt.trafficLight(LIGHT_ID, "auto");
      if (typeof window.addLog === "function") window.addLog("[MQTT] Đèn → AUTO ✓", "ok");
    } catch (e) {}
  };
}

// ═══════════════════════════════════════════════════════════════
// SEARCH — filter violations từ API (server-side)
// ═══════════════════════════════════════════════════════════════
function _patchSearch() {
  const btnSearch   = document.getElementById("btnSearch");
  const searchInput = document.getElementById("searchInput");
  if (!btnSearch) return;

  btnSearch.addEventListener("click", async () => {
    const q = (searchInput ? searchInput.value : "").trim().toUpperCase();
    if (!q) {
      // Reload all
      const vs = await API.violations.list({ limit: 200 });
      _injectViolations(vs);
      return;
    }
    // Server-side search by license plate
    const vs = await API.violations.list({ license_plate: q, limit: 100 });
    _injectViolations(vs);
    if (typeof window.toast === "function")
      window.toast(`Tìm "${q}": ${Array.isArray(vs) ? vs.length : 0} kết quả`, "info");
  });
}

// ═══════════════════════════════════════════════════════════════
// CAMERA STREAM — patch camera selector
// ═══════════════════════════════════════════════════════════════
function _patchCameraStream() {
  const camSel = document.getElementById("camSel");
  if (!camSel) return;

  camSel.addEventListener("change", async () => {
    const camId = camSel.value;
    if (!camId) return;

    // Fetch camera info
    const cam = await API.cameras.get(parseInt(camId));
    if (!cam) return;

    const streamUrl = cam.stream_url || cam.configured_stream_url;
    const camImg    = document.getElementById("camImg");

    if (streamUrl && camImg) {
      if (typeof window.stopCamSim === "function") window.stopCamSim();
      camImg.src = streamUrl;
      if (typeof window.addLog === "function")
        window.addLog(`[CAM] Chuyển sang Camera ${camId}: ${streamUrl}`, "ok");
    } else if (camImg) {
      // Thử stream feed chính
      const stStatus = await API.stream.status();
      if (stStatus && stStatus.active) {
        if (typeof window.stopCamSim === "function") window.stopCamSim();
        camImg.src = API.stream.feedUrl();
      }
    }

    // Filter violations theo camera đã chọn
    const vs = await API.violations.list({ camera_id: camId, limit: 200 });
    _injectViolations(vs);
  });
}

// ═══════════════════════════════════════════════════════════════
// TEST BUTTONS — real API calls
// ═══════════════════════════════════════════════════════════════
function _patchTestButtons() {
  const log = (msg, cls) => { if (typeof window.addLog === "function") window.addLog(msg, cls); };

  // Test camera
  const btCam = document.getElementById("btTestCam");
  if (btCam) {
    btCam.onclick = async () => {
      log("[TEST] Đang kiểm tra cameras...", "info");
      const cams = await API.cameras.list();
      if (Array.isArray(cams)) {
        if (cams.length === 0) {
          log("[TEST] Không có camera nào trong database", "warn");
        } else {
          cams.forEach(c => {
            const st  = c.status || "inactive";
            const cls = st === "active" || c.online ? "ok" : st === "error" ? "err" : "warn";
            log(`[TEST] CAM-${c.camera_id} "${c.camera_name}" — ${st.toUpperCase()} | ${c.location || "--"}`, cls);
          });
        }
      } else {
        log("[TEST] ✗ Không kết nối được database camera", "err");
      }
    };
  }

  // Test MQTT
  const btMQTT = document.getElementById("btTestMQTT");
  if (btMQTT) {
    btMQTT.onclick = async () => {
      log("[TEST] Đang kiểm tra MQTT...", "info");
      const st = await API.mqtt.status();
      if (st) {
        const cls = st.connected ? "ok" : "warn";
        log(`[TEST] MQTT: ${st.connected ? "✓ KẾT NỐI" : "✗ KHÔNG KẾT NỐI"} | Broker: ${st.broker || "--"} | Enabled: ${st.enabled}`, cls);
      } else {
        log("[TEST] ✗ Không lấy được trạng thái MQTT", "err");
      }
    };
  }

  // Test AI
  const btAI = document.getElementById("btTestAI");
  if (btAI) {
    btAI.onclick = async () => {
      log("[TEST] Đang kiểm tra AI backend...", "info");
      const h = await API.health();
      if (h) {
        const cls = h.vehicle_model_loaded ? "ok" : "warn";
        log(`[TEST] YOLOv8: ${h.vehicle_model_loaded ? "✓ LOADED" : "⚠ LOADING"} | OCR: ${h.ocr_enabled ? "ON" : "OFF"} | GPU: ${h.gpu_available ? "✓ " + h.device : "CPU"} | Status: ${h.status}`, cls);
      } else {
        log("[TEST] ✗ Backend không phản hồi", "err");
      }
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// SETTINGS PANEL — load/save system settings
// ═══════════════════════════════════════════════════════════════
async function _patchSettings() {
  // Load AI config từ /config
  const cfg = await API.config.get();
  if (cfg) {
    _setVal("cfCapture", cfg.capture_interval ? Math.round(cfg.capture_interval * 1000) : null);
    _setVal("cfOCR", cfg.ocr_thres != null ? Math.round(cfg.ocr_thres * 100) : null);
    console.log("[API] Config loaded:", cfg);
  }

  // Load system settings từ /settings
  const setts = await API.settings.list();
  if (Array.isArray(setts)) {
    setts.forEach(s => {
      // Map setting key → input field nếu có
      const inputId = _settingKeyToInputId(s.key);
      if (inputId) _setVal(inputId, s.value);
    });
  }

  // Patch Save Settings button
  const btnSave = document.getElementById("btnSaveCfg");
  if (btnSave) {
    const orig = btnSave.onclick;
    btnSave.addEventListener("click", async () => {
      // Save AI config
      const vconf = parseFloat(document.getElementById("cfOCR")?.value) / 100 || 0.7;
      await API.config.update({ ocr_thres: vconf });
      if (typeof window.addLog === "function") window.addLog("[SETTINGS] Config đã lưu vào backend ✓", "ok");
    });
  }
}

function _setVal(id, val) {
  if (val == null) return;
  const el = document.getElementById(id);
  if (el) el.value = val;
}

function _settingKeyToInputId(key) {
  const map = {
    "traffic_light.green_duration":  "cfGreen",
    "traffic_light.amber_duration":  "cfAmber",
    "traffic_light.red_duration":    "cfRed",
    "capture.interval_ms":           "cfCapture",
    "detection.speed_limit":         "cfSpeed",
    "detection.max_vehicles":        "cfVeh",
    "ocr.confidence_threshold":      "cfOCR",
  };
  return map[key] || null;
}

// ═══════════════════════════════════════════════════════════════
// LAPTOP CAMERA SNAP → /predict/frame/b64
// Patch lapDoSnapshot để gửi frame thật lên AI
// ═══════════════════════════════════════════════════════════════
function _patchLapSnapshot() {
  const origSnap = window.lapDoSnapshot;
  if (!origSnap) return;

  window.lapDoSnapshot = async function(auto = false) {
    // Lấy frame từ webcam
    const frameDataUrl = typeof window.lapGetFrameDataUrl === "function"
      ? window.lapGetFrameDataUrl()
      : "";

    if (!frameDataUrl || frameDataUrl.startsWith("data:,")) {
      if (!auto) {
        if (typeof window.toast     === "function") window.toast("Chưa có frame camera!", "warn");
        if (typeof window.lapAddLog === "function") window.lapAddLog("[SNAP] ✗ Không có frame camera", "warn");
      }
      return;
    }

    try {
      if (!auto && typeof window.lapAddLog === "function")
        window.lapAddLog("[SNAP] Đang gửi frame lên AI backend...", "info");

      // Tách base64 data
      const b64 = frameDataUrl.split(",")[1];
      if (!b64) return;

      const result = await API.violations.scanFrame(b64);

      if (result && result.detections && result.detections.length > 0) {
        const det   = result.detections[0];
        const plate = (det.license_plate || "").toUpperCase();

        if (plate && plate !== "" && typeof window.lapAddLog === "function") {
          window.lapAddLog(`[AI] Phát hiện: ${plate} (conf: ${Math.round(det.confidence * 100)}%)`, "ok");
          if (typeof window.toast === "function") window.toast(`🔍 Biển số: ${plate}`, "ok");
          // Cập nhật input
          const inp = document.getElementById("lapPlateInput");
          if (inp) inp.value = plate;
        } else if (!auto) {
          if (typeof window.lapAddLog === "function") window.lapAddLog("[AI] Không đọc được biển số", "warn");
          if (typeof window.toast     === "function") window.toast("Không đọc được biển số", "warn");
        }
      } else if (!auto) {
        if (typeof window.lapAddLog === "function") window.lapAddLog("[AI] Không phát hiện xe/biển số trong frame", "warn");
        if (typeof window.toast     === "function") window.toast("Không phát hiện xe trong frame", "warn");
      }
    } catch (e) {
      if (!auto) {
        if (typeof window.lapAddLog === "function") window.lapAddLog(`[SNAP ERROR] ${e.message}`, "err");
        if (typeof window.toast     === "function") window.toast("Lỗi AI: " + e.message, "err");
      }
    }
  };
}

// ═══════════════════════════════════════════════════════════════
// POLLING — live updates
// ═══════════════════════════════════════════════════════════════
let _polling = false;
function _startPolling() {
  if (_polling) return;
  _polling = true;

  // Violations: reload mỗi 10s
  setInterval(async () => {
    try {
      const camSel = document.getElementById("camSel");
      const camId  = camSel && camSel.value ? parseInt(camSel.value) : undefined;
      const vs = await API.violations.list({
        camera_id: camId,
        limit: 200,
      });
      if (Array.isArray(vs) && vs.length > 0) _injectViolations(vs);
    } catch(e) {}
  }, 10000);

  // Cameras: reload mỗi 20s
  setInterval(async () => {
    try {
      const cams = await API.cameras.summary();
      if (Array.isArray(cams)) _injectCameras(cams);
    } catch(e) {}
  }, 20000);

  // Health + MQTT: mỗi 30s
  setInterval(async () => {
    try {
      const h = await API.health();
      _updateHealthUI(h);
      const m = await API.mqtt.status();
      _updateMQTT(m);
    } catch(e) {}
  }, 30000);

  // Stream status: mỗi 5s
  setInterval(async () => {
    try {
      const st = await API.stream.status();
      _updateStream(st);
    } catch(e) {}
  }, 5000);

  // Daily stats: mỗi 2 phút
  setInterval(_loadDailyStats, 120000);

  console.log("[API] Polling started ✓");
}

// ═══════════════════════════════════════════════════════════════
// BOOT — chạy sau main.js boot() (1.5s delay)
// ═══════════════════════════════════════════════════════════════
async function _apiBoot() {
  console.log("[API] Real backend boot v2.0 starting...");
  if (typeof window.addLog === "function") window.addLog("[API] Real backend layer v2.0 khởi động...", "info");

  // 1. Health check
  const health = await API.health();
  _updateHealthUI(health);
  if (health) {
    if (typeof window.espOK !== "undefined") window.espOK = true;
    if (typeof window.isDemo !== "undefined") window.isDemo = false;
    const banner = document.getElementById("demoBanner");
    if (banner) banner.classList.add("hidden");
    if (typeof window.addLog === "function")
      window.addLog(`[API] ✓ Backend: ${health.status} | Supabase: ${health.supabase_connected ? "✓" : "✗"} | GPU: ${health.gpu_available ? health.device : "CPU"} | Model: ${health.vehicle_model_loaded ? "✓ Loaded" : "Loading..."}`, health.vehicle_model_loaded ? "ok" : "warn");
  } else {
    if (typeof window.addLog === "function") window.addLog("[API] ⚠ Backend chưa phản hồi — tiếp tục polling...", "warn");
  }

  // 2. Load violations
  const vs = await API.violations.list({ limit: 200 });
  _injectViolations(vs);

  // 3. Load cameras (summary view)
  const cams = await API.cameras.summary();
  _injectCameras(cams);

  // 4. MQTT status
  const mqttSt = await API.mqtt.status();
  _updateMQTT(mqttSt);

  // 5. Stream status
  const streamSt = await API.stream.status();
  _updateStream(streamSt);

  // 6. Daily stats for charts
  await _loadDailyStats();

  // 7. Settings
  await _patchSettings();

  // 8. Start polling
  _startPolling();

  if (typeof window.toast === "function") window.toast("✅ Backend API Connected", "ok");
  if (typeof window.addLog === "function") window.addLog("[API] ✓ Real backend layer v2.0 ready — Supabase + FastAPI", "ok");
  console.log("[API] Real backend boot v2.0 complete ✓");
}

// ═══════════════════════════════════════════════════════════════
// ENTRY POINT
// ═══════════════════════════════════════════════════════════════
window.addEventListener("DOMContentLoaded", () => {
  setTimeout(async () => {
    await _apiBoot();
    _patchTrafficLights();
    _patchCameraStream();
    _patchSearch();
    _patchLapSnapshot();
    _patchTestButtons();
  }, 1500);
});
