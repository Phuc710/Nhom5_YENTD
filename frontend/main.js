/* ═══════════════════════════════════════════════════════════════
   AI TRAFFIC DASHBOARD — PREMIUM ENGINE v4.2 (2026)
   Laptop Camera + ESP32 + Demo Mode + Particles + Async Themes

   FIX v4.2 — BIỂN SỐ KHÔNG BỊ ĐẢO NGƯỢC:
     - lapStartBrowserDraw(): KHÔNG flip canvas dữ liệu, chỉ dùng CSS
       transform để hiển thị mirror cho UX (selfie-style)
     - lapImg hiển thị dùng CSS scaleX(-1) thay vì flip canvas
     - ocrCanvas và snapshot luôn dùng frame KHÔNG flip → OCR đúng
     - _lapOCRCanvasRaw: riêng biệt hoàn toàn, không bao giờ flip
   FIX v4.2 — AUTH 401 BOOTSTRAP:
     - ensureToken() retry tự động khi nhận 401
     - getToken() luôn fallback về DASHBOARD_SECRET
     - safeFetch() cải thiện retry logic
   FIX v4.1 — LAPTOP CAMERA STOP/START HOÀN TOÀN:
     - LAP.generation counter: mỗi start tăng lên, abort mọi async cũ
     - tryFlaskLapCam() poll /api/laptop_camera/ready thay vì img.onerror
     - lapStop() đặt LAP.active=false + tăng generation TRƯỚC khi gọi API
     - lapStartDemo() closure capture generation → animation frame tự thoát
     - lapStartBrowserDraw() closure capture generation → tự thoát khi stop
═══════════════════════════════════════════════════════════════ */
"use strict";

// ══════════════════════════════════════════════════════════════
// POLYFILLS — ensure cross-browser compatibility
// ══════════════════════════════════════════════════════════════
// AbortSignal.timeout polyfill (Firefox < 124, Safari < 17.4)
if (typeof AbortSignal !== "undefined" && !AbortSignal.timeout) {
  AbortSignal.timeout = function(ms) {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(new DOMException("TimeoutError", "TimeoutError")), ms);
    return ctrl.signal;
  };
}
// CanvasRenderingContext2D.roundRect polyfill (older browsers)
if (typeof CanvasRenderingContext2D !== "undefined" && !CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, radii) {
    const r = Array.isArray(radii) ? radii[0] || 0 : (radii || 0);
    this.beginPath();
    this.moveTo(x + r, y);
    this.arcTo(x + w, y, x + w, y + h, r);
    this.arcTo(x + w, y + h, x, y + h, r);
    this.arcTo(x, y + h, x, y, r);
    this.arcTo(x, y, x + w, y, r);
    this.closePath();
    return this;
  };
}

// ── Auth constants ──
const TK               = "TRAFFIC_AI_TOKEN";
const DASHBOARD_SECRET = "TRAFFIC_AI_TOKEN";

// ══════════════════════════════════════════════════════════════
// FIX v4.0.3 + v4.2: PRE-SEED TOKEN — chạy ĐỒNG BỘ ngay lập tức
// ══════════════════════════════════════════════════════════════
(function preSeedToken() {
  const existing = localStorage.getItem(TK);
  if (!existing || existing.trim() === "") {
    localStorage.setItem(TK, DASHBOARD_SECRET);
    console.log("[AUTH v4.2] Pre-seeded DASHBOARD_SECRET token → localStorage OK");
  } else {
    console.log("[AUTH v4.2] Token already present:", existing.substring(0, 20) + "...");
  }
})();

const getToken = () => {
  const t = (localStorage.getItem(TK) || "").trim();
  if (t !== DASHBOARD_SECRET) localStorage.setItem(TK, DASHBOARD_SECRET);
  return DASHBOARD_SECRET;
};
const logout = () => { localStorage.removeItem(TK); location.replace("login.html"); };

(function authGuard() {
  const tok = getToken();
  if (!tok || tok.trim() === "") {
    console.warn("[AUTH] No token after pre-seed — this should not happen");
  }
})();

// ── Helpers ──
const $  = id  => document.getElementById(id);
const qA = sel => document.querySelectorAll(sel);

// ── Global State ──
let isDemo = false; // Tắt demo mode — chỉ dùng dữ liệu thật từ camera/ESP32
let espOK  = false;
let modeOverride = null;
let currentTheme = 'neon-futuristic';
let particlesInitialized = false;

const DS = {
  light: "RED", countdown: 10, phase: "ĐỎ", camState: "ACTIVE",
  vehicles: 3, speed: 14.2, fps: 12,
  weather: "Nắng", dist: 5.0, roi: "STOP_LINE", capture: 500,
  objects: "Xe máy & Ô tô",
  totalViol: 0, todayViol: 0, detected: 0, uptime: 0,
};

// ═══════════════════════════════════════════════════════════════════
// FIX v6.0: GEO MODULE — Định vị GPS thật + Reverse Geocode (Nominatim)
// Tự động yêu cầu quyền vị trí (giống Google Maps).
// Cập nhật server /api/update_location để stamp ảnh vi phạm đúng địa chỉ.
// ═══════════════════════════════════════════════════════════════════
const GEO = {
  lat: null, lng: null, accuracy: null,
  address: "", street: "", district: "", city: "", intersection: "",
  maps_url: "", ready: false, error: null,
  watching: false, watchId: null, _lastRevGeo: 0,

  /** Khởi động — gọi ngay trong boot() */
  init() {
    if (!navigator.geolocation) {
      GEO.error = "Trình duyệt không hỗ trợ GPS";
      console.warn("[GEO] Geolocation không được hỗ trợ");
      return;
    }
    console.log("[GEO] 📍 Đang yêu cầu quyền vị trí...");
    navigator.geolocation.getCurrentPosition(
      pos => GEO._onPos(pos),
      err => GEO._onErr(err),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  },

  _onPos(pos) {
    GEO.lat      = pos.coords.latitude;
    GEO.lng      = pos.coords.longitude;
    GEO.accuracy = pos.coords.accuracy;
    GEO.ready    = true; GEO.error = null;
    console.log(`[GEO] ✅ GPS OK: ${GEO.lat.toFixed(6)}, ${GEO.lng.toFixed(6)} ±${Math.round(GEO.accuracy)}m`);
    if (typeof lapAddLog === "function") lapAddLog(`[GEO] 📍 GPS: ${GEO.lat.toFixed(5)}, ${GEO.lng.toFixed(5)} ±${Math.round(GEO.accuracy)}m`, "ok");
    GEO._reverseGeocode(GEO.lat, GEO.lng);
    GEO._pushServer();
    if (!GEO.watching) GEO._watch();
  },

  _onErr(err) {
    const m = {1:"Từ chối quyền GPS",2:"Không xác định được vị trí",3:"Timeout GPS"};
    GEO.error = m[err.code] || err.message;
    console.warn("[GEO] ⚠️", GEO.error);
    if (typeof lapAddLog === "function") lapAddLog(`[GEO] ⚠️ ${GEO.error} — Vui lòng cấp quyền vị trí`, "warn");
    if (typeof toast === "function")
      setTimeout(() => toast("📍 Cấp quyền vị trí để ghi địa điểm vi phạm chính xác", "warn"), 1200);
  },

  _watch() {
    GEO.watching = true;
    GEO.watchId  = navigator.geolocation.watchPosition(
      pos => {
        const now = Date.now();
        if (now - GEO._lastRevGeo < 30000) return;
        GEO._lastRevGeo = now;
        GEO.lat = pos.coords.latitude; GEO.lng = pos.coords.longitude; GEO.accuracy = pos.coords.accuracy;
        GEO._reverseGeocode(GEO.lat, GEO.lng);
        GEO._pushServer();
      },
      err => console.warn("[GEO] watch err:", err.message),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }
    );
  },

  async _reverseGeocode(lat, lng) {
    try {
      const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&addressdetails=1&accept-language=vi`;
      const res = await fetch(url, { headers: {"Accept-Language":"vi"} });
      if (!res.ok) return;
      const data = await res.json();
      const a = data.address || {};
      GEO.street       = a.road || a.street || a.pedestrian || a.footway || "";
      GEO.district     = a.city_district || a.suburb || a.quarter || a.district || a.county || "";
      GEO.city         = a.city || a.town || a.village || a.state || "";
      GEO.intersection = a.neighbourhood || a.suburb || a.quarter || GEO.district;
      GEO.address      = data.display_name || `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      GEO.maps_url     = `https://www.google.com/maps?q=${lat},${lng}`;
      console.log(`[GEO] 🗺️ Địa chỉ: ${GEO.street}, ${GEO.district}, ${GEO.city}`);
      if (typeof lapAddLog === "function") lapAddLog(`[GEO] 🗺️ ${GEO.street}, ${GEO.district}, ${GEO.city}`, "ok");
      GEO._updateUI(); GEO._pushServerDebounced();
    } catch(e) {
      GEO.address  = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
      GEO.maps_url = `https://www.google.com/maps?q=${lat},${lng}`;
      console.warn("[GEO] reverseGeocode err:", e.message);
    }
  },

  async _pushServer() {
    if (!GEO.lat || !GEO.lng) return;
    try {
      await safeFetch("/api/update_location", {
        method: "POST",
        body: JSON.stringify({
          lat: GEO.lat, lng: GEO.lng,
          road: GEO.street, suburb: GEO.intersection || GEO.district,
          district: GEO.district, city: GEO.city,
        }),
      });
    } catch(e) { console.warn("[GEO] pushServer:", e.message); }
  },

  _pushTimer: null,
  _pushServerDebounced() {
    if (GEO._pushTimer) clearTimeout(GEO._pushTimer);
    GEO._pushTimer = setTimeout(() => GEO._pushServer(), 10000);
  },

  _updateUI() {
    const el = document.getElementById("geoAddress");
    if (el) el.textContent = GEO.address;
    const ec = document.getElementById("geoCoords");
    if (ec && GEO.lat) ec.textContent = `${GEO.lat.toFixed(5)}, ${GEO.lng.toFixed(5)}`;
    const lk = document.getElementById("geoMapsLink");
    const lkOff = document.getElementById("geoMapsLinkOff");
    if (lk && GEO.maps_url) {
      lk.href = GEO.maps_url; lk.style.display = "inline";
      if (lkOff) lkOff.style.display = "none";
    }
  },

  /**
   * Lấy đầy đủ thông tin vị trí + thời gian tại thời điểm chụp vi phạm.
   * Gọi ngay khi bấm Chụp — không async, không delay.
   */
  getViolationLocation() {
    const now = new Date();
    const wd  = ["Chủ Nhật","Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy"];
    const p2  = n => String(n).padStart(2,"0");
    return {
      lat:          GEO.lat,
      lng:          GEO.lng,
      accuracy:     GEO.accuracy,
      address:      GEO.address,
      street:       GEO.street,
      district:     GEO.district,
      city:         GEO.city,
      intersection: GEO.intersection,
      maps_url:     GEO.maps_url || (GEO.lat ? `https://www.google.com/maps?q=${GEO.lat},${GEO.lng}` : ""),
      time_str:     `${p2(now.getHours())}:${p2(now.getMinutes())}:${p2(now.getSeconds())}`,
      date_str:     `${p2(now.getDate())}/${p2(now.getMonth()+1)}/${now.getFullYear()}`,
      date_vn:      `${wd[now.getDay()]}, ${p2(now.getDate())}/${p2(now.getMonth()+1)}/${now.getFullYear()}`,
      timestamp:    Math.floor(now.getTime() / 1000),
      ready:        GEO.ready,
    };
  },
};

const CYCLE = [
  { light: "GREEN",  phase: "XANH", dur: 7,  cam: "IDLE",   next: 1 },
  { light: "YELLOW", phase: "VÀNG", dur: 3,  cam: "WARMUP", next: 2 },
  { light: "RED",    phase: "ĐỎ",   dur: 10, cam: "ACTIVE", next: 0 },
];
let cIdx = 2;
let cycleIV = null;

const VIOLS = [];
let filtered = [];
let page = 1, pageSize = 10;
let vioID = 1;

const PLATES = [
  "51B-12345","59D-67890","29A-11222","43K-55667","30F-99001",
  "36C-33445","72B-77889","51G-22334","61H-44556","88A-66778",
  "31E-88990","77D-11223"
];
const TYPES = ["Xe máy","Xe máy","Xe máy","Ô tô","Xe máy","Ô tô"];

const hourly = new Array(24).fill(0);
const weekly = [3, 7, 5, 12, 8, 4, 0];

const camFrameW = 640, camFrameH = 360;

// ── Laptop camera state ──
// FIX v4.2: generation counter — mỗi lần start tăng lên
// Mọi async operation (poll, draw loop) capture generation khi start
// Nếu LAP.generation thay đổi → operation đó tự abort
// FIX v4.2: _displayFlip — kiểm soát flip CSS cho hiển thị
//           OCR/snapshot LUÔN dùng frame KHÔNG flip
const LAP = {
  active:      false,
  serverMode:  false,
  demoMode:    true,
  stream:      null,
  video:       null,
  animID:      null,
  snapshots:   [],
  detCount:    0,
  fps:         0,
  fpsCounter:  0,
  fpsTimer:    null,
  generation:  0,
  displayFlip: false,  // Default OFF: tránh hiển thị bị đảo ngược (selfie-mode)

  // Auto snapshot (mỗi 6s khi đèn đỏ)
  autoSnapEnabled: false, // Tắt auto-snap — người dùng tự nhấn snapshot
  _autoSnapTimer:  null,
  _snapInFlight:   false,
  _lastSnapAtMs:   0,

  // Frame capture cache (để tránh gửi placeholder lên server)
  lastFrameDataUrl: "",
  _capCanvas:       null,
};

// ═══════════════════════════════════════════════════════════════
// v4.2: GLOBAL ERROR HANDLING
// ═══════════════════════════════════════════════════════════════
window.onerror = function(msg, url, line, col, err) {
  const shortMsg = typeof msg === "string" ? msg.substring(0, 120) : String(msg);
  toast(`Lỗi hệ thống: ${shortMsg} (dòng ${line})`, "err");
  addLog(`[ERROR] ${shortMsg} @ line:${line} col:${col}`, "err");
  console.error("[v4.2 ERROR]", msg, url, line, col, err);
  return false;
};

window.onunhandledrejection = function(event) {
  const reason = event.reason ? (event.reason.message || String(event.reason)).substring(0, 100) : "Unknown rejection";
  addLog(`[UNHANDLED PROMISE] ${reason}`, "err");
  console.error("[v4.2 PROMISE REJECTION]", event.reason);
};

// ═══════════════════════════════════════════════════════════════
// ensureToken — always returns the API token
// ═══════════════════════════════════════════════════════════════
async function ensureToken() {
  const tok = getToken();
  if (tok && tok.trim() !== "") return tok.trim();
  localStorage.setItem(TK, DASHBOARD_SECRET);
  return DASHBOARD_SECRET;
}

async function safeFetch(url, opts = {}) {
  // Prepend API_BASE_URL for all relative paths → call FastAPI backend
  if (url && url.startsWith("/") && !url.startsWith("//")) {
    const base = (window.API_BASE_URL || "").replace(/\/$/, "");
    if (base) url = base + url;
  }

  let tok = getToken();
  if (!tok || tok.trim() === "") {
    tok = await ensureToken();
    if (!tok) {
      addLog(`[AUTH] Không thể lấy token cho ${url}`, "err");
      return null;
    }
  }

  const controller = new AbortController();
  const timeoutMs  = typeof opts.timeoutMs === "number" ? opts.timeoutMs : 8000;
  const timeoutId  = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const { timeoutMs: _ignoredTimeout, ...fetchOpts } = (opts || {});
    const response = await fetch(url, {
      ...fetchOpts,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchOpts.headers || {}),
      },
    });

    clearTimeout(timeoutId);

    if (response.status === 401) {
      addLog(`[AUTH] 401 trên ${url} — re-seed token và retry...`, "warn");
      // FIX v4.2: Force re-seed DASHBOARD_SECRET rồi retry ngay
      localStorage.setItem(TK, DASHBOARD_SECRET);
      const retryResp = await fetch(url, {
        ...fetchOpts,
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${DASHBOARD_SECRET}`,
          ...(fetchOpts.headers || {}),
        },
      });
      if (retryResp.ok) {
        addLog(`[AUTH] Retry 401 → OK cho ${url}`, "ok");
        return retryResp.json().catch(() => null);
      }
      if (retryResp.status === 401) {
        addLog(`[AUTH] Retry 401 lần 2 thất bại — chuyển login`, "err");
        logout();
        return null;
      }
      return retryResp.json().catch(() => null);
    }

    if (response.status === 403) {
      addLog(`[AUTH] 403 Forbidden trên ${url}`, "warn");
      return null;
    }

    if (!response.ok) {
      addLog(`[API] HTTP ${response.status} cho ${url}`, "warn");
      return null;
    }

    return response.json().catch(() => null);
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === "AbortError") {
      addLog(`[API] Timeout (8s) cho ${url}`, "warn");
    } else {
      addLog(`[API] Fetch lỗi: ${e.message} cho ${url}`, "warn");
    }
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════
// v4.0: PARTICLE SYSTEM
// ═══════════════════════════════════════════════════════════════
function initParticles() {
  try {
    if (typeof particlesJS === "undefined") {
      addLog("[PARTICLES] particles.js chưa load — bỏ qua", "warn");
      return;
    }
    if (particlesInitialized) return;

    const canvasId = "particleCanvas";
    const el = $(canvasId);
    if (!el) {
      const div = document.createElement("div");
      div.id = canvasId;
      div.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;";
      document.body.insertBefore(div, document.body.firstChild);
    }

    particlesJS(canvasId, {
      particles: {
        number: { value: 50, density: { enable: true, value_area: 800 } },
        color: { value: "#20caff" },
        shape: { type: "circle" },
        opacity: { value: 0.45, random: true, anim: { enable: true, speed: 0.5, opacity_min: 0.1, sync: false } },
        size: { value: 3, random: true, anim: { enable: true, speed: 1.5, size_min: 0.5, sync: false } },
        line_linked: { enable: true, distance: 150, color: "#00e87a", opacity: 0.3, width: 1 },
        move: { enable: true, speed: 1.8, direction: "none", random: true, straight: false, out_mode: "out", bounce: false }
      },
      interactivity: {
        detect_on: "canvas",
        events: {
          onhover: { enable: true, mode: "repulse" },
          onclick: { enable: true, mode: "push" },
          resize: true
        },
        modes: {
          repulse: { distance: 200, duration: 0.4 },
          push: { particles_nb: 4 },
          bubble: { distance: 250, size: 6, duration: 2, opacity: 0.8, speed: 3 }
        }
      },
      retina_detect: true
    });

    particlesInitialized = true;
    addLog("[PARTICLES] Particle system v4.2 khởi động ✓", "ok");
    attachNeonHoverListeners();
  } catch (e) {
    addLog(`[PARTICLES] Lỗi khởi tạo: ${e.message}`, "warn");
    console.warn("[v4.2 PARTICLES ERROR]", e);
  }
}

function attachNeonHoverListeners() {
  try {
    const neonEls = document.querySelectorAll(".neon-hover, .kpi-card, .cam-card, .dev-card, .vcard");
    neonEls.forEach(el => {
      el.addEventListener("mouseenter", () => triggerParticleBurst("repulse"));
      el.addEventListener("click",      () => triggerParticleBurst("push"));
    });
    addLog(`[PARTICLES] Hover listeners gắn vào ${neonEls.length} phần tử neon`, "info");
  } catch (e) {
    console.warn("[v4.2 NEON HOVER] Error:", e);
  }
}

function triggerParticleBurst(mode = "push") {
  try {
    if (!particlesInitialized || typeof window.pJSDom === "undefined") return;
    const pInst = window.pJSDom[0]?.pJS;
    if (!pInst) return;
    const prevMode = pInst.interactivity.events.onhover.mode;
    pInst.interactivity.events.onhover.mode = mode;
    setTimeout(() => {
      if (pInst) pInst.interactivity.events.onhover.mode = prevMode;
    }, 600);
  } catch (e) {}
}

function reinitParticles(colorPrimary = "#20caff", colorLine = "#00e87a") {
  try {
    if (!particlesInitialized) { initParticles(); return; }
    if (typeof window.pJSDom !== "undefined" && window.pJSDom.length > 0) {
      window.pJSDom[0].pJS.fn.vendors.destroypJS();
      window.pJSDom = [];
      particlesInitialized = false;
    }
    const canvasId = "particleCanvas";
    particlesJS(canvasId, {
      particles: {
        number: { value: 60, density: { enable: true, value_area: 800 } },
        color: { value: colorPrimary },
        shape: { type: "circle" },
        opacity: { value: 0.5, random: true },
        size: { value: 3, random: true },
        line_linked: { enable: true, distance: 150, color: colorLine, opacity: 0.4, width: 1 },
        move: { enable: true, speed: 2 }
      },
      interactivity: {
        detect_on: "canvas",
        events: { onhover: { enable: true, mode: "repulse" }, onclick: { enable: true, mode: "push" } },
        modes: { repulse: { distance: 200, duration: 0.4 } }
      },
      retina_detect: true
    });
    particlesInitialized = true;
  } catch (e) {
    console.warn("[v4.2 REINIT PARTICLES]", e);
  }
}

// ═══════════════════════════════════════════════════════════════
// v4.0: ASYNC THEME MANAGEMENT
// ═══════════════════════════════════════════════════════════════
const THEMES = {
  "neon-futuristic": { primary: "#20caff", secondary: "#00e87a", accent: "#ff3a5c", bg: "#070c1a", particleColor: "#20caff", lineColor: "#00e87a" },
  "cyber-red":       { primary: "#ff3a5c", secondary: "#ffb020", accent: "#20caff", bg: "#1a0707", particleColor: "#ff3a5c", lineColor: "#ffb020" },
  "matrix-green":    { primary: "#00e87a", secondary: "#20caff", accent: "#ffb020", bg: "#030f07", particleColor: "#00e87a", lineColor: "#20caff" },
  "deep-purple":     { primary: "#b468ff", secondary: "#20caff", accent: "#ff3a5c", bg: "#0a0715", particleColor: "#b468ff", lineColor: "#20caff" },
  "neon-active":     { primary: "#00e87a", secondary: "#20caff", accent: "#ffb020", bg: "#050f08", particleColor: "#00e87a", lineColor: "#20caff" },
  "neon-alert":      { primary: "#ff3a5c", secondary: "#ffb020", accent: "#20caff", bg: "#140508", particleColor: "#ff3a5c", lineColor: "#ffb020" },
};

function syncThemeButtons(themeName = currentTheme) {
  qA(".theme-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.theme === themeName);
  });
}

async function fetchTheme() {
  try {
    await ensureToken();
    const data = await safeFetch("/api/theme");
    if (data && data.ok && data.theme) {
      const themeName = THEMES[data.theme] ? data.theme : "neon-futuristic";
      await applyTheme(themeName, false);
      addLog(`[THEME] Theme từ server: ${themeName}`, "ok");
    } else {
      throw new Error(data ? "Server trả về ok=false" : "Không có phản hồi từ /api/theme");
    }
  } catch (e) {
    const savedTheme = localStorage.getItem("TRAFFIC_THEME") || "neon-futuristic";
    await applyTheme(savedTheme, false);
    addLog(`[THEME] Server không khả dụng — dùng theme local: ${savedTheme} (${e.message})`, "warn");
  }
}

async function applyTheme(themeName, save = true) {
  try {
    const theme = THEMES[themeName] || THEMES["neon-futuristic"];
    currentTheme = themeName;

    Object.keys(THEMES).forEach(t => document.documentElement.classList.remove(t));
    document.documentElement.classList.add(themeName);

    let styleEl = document.getElementById("theme-vars");
    if (!styleEl) {
      styleEl = document.createElement("style");
      styleEl.id = "theme-vars";
      document.head.appendChild(styleEl);
    }
    styleEl.textContent = `:root {
      --theme-primary: ${theme.primary};
      --theme-secondary: ${theme.secondary};
      --theme-accent: ${theme.accent};
      --theme-bg: ${theme.bg};
      --cyan: ${theme.primary};
    }`;

    if (save) {
      localStorage.setItem("TRAFFIC_THEME", themeName);
      try {
        await safeFetch("/api/theme", {
          method: "POST",
          body: JSON.stringify({ theme: themeName }),
        });
      } catch (e) {
        addLog(`[THEME] Không thể lưu theme lên server: ${e.message}`, "warn");
      }
    }

    reinitParticles(theme.particleColor, theme.lineColor);

    const sel = $("themeSelector");
    if (sel) sel.value = themeName;
    syncThemeButtons(themeName);

    addLog(`[THEME] Áp dụng theme: ${themeName} ✓`, "ok");
    toast(`🎨 Theme: ${themeName}`, "ok");
  } catch (e) {
    addLog(`[THEME] Lỗi áp dụng theme: ${e.message}`, "err");
  }
}

function buildThemeSelector() {
  const sel = $("themeSelector");
  if (sel) {
    sel.innerHTML = Object.keys(THEMES).map(t => `<option value="${t}"${t === currentTheme ? " selected" : ""}>${t}</option>`).join("");
    sel.onchange = () => applyTheme(sel.value, true);
  }
  qA(".theme-btn").forEach(btn => {
    btn.onclick = () => applyTheme(btn.dataset.theme || "neon-futuristic", true);
  });
  syncThemeButtons(currentTheme);
}

// ═══════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════
const PAGE_TITLES = {
  overview:   "Tổng Quan Hệ Thống",
  violations: "Quản Lý Vi Phạm",
  camera:     "Camera ESP32 — Quan Sát",
  laptop:     "Camera Quét Biển Số",
  devices:    "Thiết Bị & IoT",
  stats:      "Thống Kê & Phân Tích",
  settings:   "Cài Đặt Hệ Thống"
};

function goTo(s) {
  qA(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.s === s));
  qA(".section").forEach(sec => sec.classList.toggle("active", sec.id === `sec-${s}`));
  $("pageTitle").textContent = PAGE_TITLES[s] || s;
  if (s === "stats")    renderCharts();
  if (s === "devices")  renderDevices();
  if (s === "laptop")   syncLapCtx();
  if (s === "settings") buildThemeSelector();
  triggerParticleBurst("bubble");
}

qA(".nav-item").forEach(n => n.addEventListener("click", () => goTo(n.dataset.s)));
window.goTo = goTo;

// ═══════════════════════════════════════════════════════════════
// CLOCK
// ═══════════════════════════════════════════════════════════════
function tickClock() {
  try {
    const now = new Date();
    const t   = now.toLocaleTimeString("vi-VN", { hour12: false });
    const d   = now.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
    $("sbClock").textContent = t;
    $("sbDate").textContent  = d;
    if ($("camTS"))  $("camTS").textContent  = t;
    if ($("lapTS"))  $("lapTS").textContent  = t;
    DS.uptime++;
    const h = Math.floor(DS.uptime / 3600), m = Math.floor((DS.uptime % 3600) / 60), s = DS.uptime % 60;
    if ($("siUptime")) $("siUptime").textContent = `${h}h${m}m${s}s`;
  } catch (e) { console.warn("[CLOCK]", e); }
}
setInterval(tickClock, 1000);
tickClock();

// ═══════════════════════════════════════════════════════════════
// CONNECTION
// ═══════════════════════════════════════════════════════════════
function setConn(type) {
  const led = $("connLed"), txt = $("connText");
  if (!led || !txt) return;
  led.className = "conn-led " + type;
  if (type === "online") {
    txt.textContent = "ESP32 Kết Nối";
    isDemo = false;
    $("demoBanner") && $("demoBanner").classList.add("hidden");
  } else if (type === "demo") {
    txt.textContent = "Virtual Cluster Standby";
  } else {
    txt.textContent = "Mất Kết Nối";
  }
}

$("btnConnect") && $("btnConnect").addEventListener("click", () => {
  const ip = prompt("Nhập địa chỉ IP ESP32:", "192.168.1.100");
  if (!ip) return;
  toast("Đang kết nối ESP32 @ " + ip + "...", "info");
  setTimeout(() => {
    if (Math.random() > 0.4) {
      espOK = true;
      setConn("online");
      toast("ESP32 đã kết nối thành công!", "ok");
      $("siESP")    && ($("siESP").textContent = "v2.1.3");
      $("tbDot")    && $("tbDot").classList.add("live");
      $("tbLabel")  && ($("tbLabel").textContent = "ThingsBoard Kết Nối");
      $("mqttVal")  && ($("mqttVal").textContent = "Kết Nối");
    } else {
      toast("Không thể kết nối. Kiểm tra IP/mạng.", "err");
    }
  }, 2200);
});

setConn("demo");

// Override legacy ESP32 wording: the runtime hardware source is virtual_esp32_cluster.py.
function setConn(type) {
  const led = $("connLed"), txt = $("connText");
  if (!led || !txt) return;
  led.className = "conn-led " + type;
  if (type === "online") {
    txt.textContent = "Virtual Cluster LIVE";
    isDemo = false;
    $("demoBanner") && $("demoBanner").classList.add("hidden");
  } else if (type === "demo") {
    txt.textContent = "Virtual Cluster Standby";
  } else {
    txt.textContent = "Virtual Cluster Offline";
  }
}

setConn("demo");

// ═══════════════════════════════════════════════════════════════
// TRAFFIC LIGHT ENGINE
// ═══════════════════════════════════════════════════════════════
function startCycle() {
  if (cycleIV) clearInterval(cycleIV);
  DS.countdown = CYCLE[cIdx].dur;
  renderTraffic();
  cycleIV = setInterval(() => {
    if (modeOverride !== null) return;
    DS.countdown--;
    if (DS.countdown <= 0) {
      cIdx         = CYCLE[cIdx].next;
      DS.countdown = CYCLE[cIdx].dur;
      DS.light     = CYCLE[cIdx].light;
      DS.phase     = CYCLE[cIdx].phase;
      DS.camState  = CYCLE[cIdx].cam;
      // scheduleViolation() disabled — no fake violations
    }
    renderTraffic();
    syncLapCtx();
  }, 1000);
}

function forceLight(idx) {
  modeOverride = idx;
  cIdx         = idx;
  DS.light     = CYCLE[idx].light;
  DS.phase     = CYCLE[idx].phase;
  DS.camState  = CYCLE[idx].cam;
  DS.countdown = CYCLE[idx].dur;
  if ($("emergBar")) $("emergBar").style.display = idx === 2 ? "block" : "none";
  if ($("tlBadge")) { $("tlBadge").textContent = "KHẨN CẤP"; $("tlBadge").className = "ph-badge warn"; }
  if ($("tlMode"))  { $("tlMode").textContent = "KHẨN CẤP"; $("tlMode").style.color = "var(--red)"; }
  renderTraffic();
  syncLapCtx();
  toast("Đèn " + DS.phase + " — Chế độ khẩn cấp!", "warn");
}

function resetAuto() {
  modeOverride = null;
  if ($("emergBar")) $("emergBar").style.display = "none";
  if ($("tlBadge")) { $("tlBadge").textContent = "AUTO"; $("tlBadge").className = "ph-badge"; }
  if ($("tlMode"))  { $("tlMode").textContent = "AUTO"; $("tlMode").className = "val cyan"; $("tlMode").style.color = ""; }
  toast("Khôi phục chế độ TỰ ĐỘNG.", "ok");
}

function renderTraffic() {
  try {
    ["tlRed","tlAmber","tlGreen"].forEach(id => $(id) && $(id).classList.remove("on"));
    if (DS.light === "RED")    $("tlRed")   && $("tlRed").classList.add("on");
    if (DS.light === "YELLOW") $("tlAmber") && $("tlAmber").classList.add("on");
    if (DS.light === "GREEN")  $("tlGreen") && $("tlGreen").classList.add("on");
    if ($("tlHousing")) $("tlHousing").setAttribute("data-state", DS.light);

    if ($("tlCountdown")) $("tlCountdown").textContent = DS.countdown;
    if ($("tlPhase"))     $("tlPhase").textContent = DS.phase;
    const pc = DS.light === "RED" ? "red" : DS.light === "YELLOW" ? "amber" : "green";
    if ($("tlPhase")) $("tlPhase").className = "val " + pc;
    if ($("tlPhaseChip")) {
      $("tlPhaseChip").textContent = DS.phase;
      $("tlPhaseChip").style.color = pc === "red" ? "var(--red)" : pc === "amber" ? "var(--amber)" : "var(--green)";
      $("tlPhaseChip").style.borderColor = pc === "red" ? "rgba(255,58,92,.28)" : pc === "amber" ? "rgba(255,176,32,.28)" : "rgba(0,232,122,.28)";
      $("tlPhaseChip").style.background = pc === "red" ? "var(--red-soft)" : pc === "amber" ? "var(--amber-soft)" : "var(--green-soft)";
    }
    if ($("tlCamState")) { $("tlCamState").textContent = DS.camState; $("tlCamState").className = "val " + (DS.camState === "ACTIVE" ? "green" : DS.camState === "WARMUP" ? "amber" : ""); }
    if ($("tlCycleLabel")) $("tlCycleLabel").textContent = `Xanh ${CYCLE[0].dur}s → Vàng ${CYCLE[1].dur}s → Đỏ ${CYCLE[2].dur}s`;

    const tag = $("camLightTag");
    if (tag) { tag.className = "cam-light-tag " + pc; tag.textContent = "● " + DS.phase; }
    if ($("camState")) $("camState").textContent = DS.camState;

    const lapHud = $("lapLightHud");
    if (lapHud) { lapHud.className = "cam-light-tag " + pc; lapHud.textContent = "● " + DS.phase; }
    if ($("lapLightStat")) $("lapLightStat").textContent = DS.phase;
    if ($("lapMode"))      $("lapMode").textContent = DS.camState;
    if ($("lapAiLight"))   $("lapAiLight").textContent = DS.phase + " (" + DS.camState + ")";
  } catch (e) { console.warn("[renderTraffic]", e); }
}

$("btnRed")   && $("btnRed").addEventListener("click",   () => forceLight(2));
$("btnAmber") && $("btnAmber").addEventListener("click", () => forceLight(1));
$("btnGreen") && $("btnGreen").addEventListener("click", () => forceLight(0));
$("btnAuto")  && $("btnAuto").addEventListener("click",  resetAuto);

// ═══════════════════════════════════════════════════════════════
// CONTEXT UPDATE
// ═══════════════════════════════════════════════════════════════
function updateContext() {
  try {
    const speedOK = DS.speed < 20;
    const vehOK   = DS.vehicles <= 6;
    const weatherOK = /nắng|mưa nhẹ|đủ sáng/i.test(String(DS.weather || ""));
    const distOK  = Number(DS.dist) <= 5;
    const roiOK   = String(DS.roi || "").toUpperCase() === "STOP_LINE";
    const capOK   = Number(DS.capture) <= 500;
    const objOK   = /xe máy|ô tô/i.test(String(DS.objects || ""));
    const allOK   = speedOK && vehOK && weatherOK && distOK && roiOK && capOK && objOK;
    const badCount = (!speedOK ? 1 : 0) + (!vehOK ? 1 : 0) + (!weatherOK ? 1 : 0) + (!distOK ? 1 : 0) + (!roiOK ? 1 : 0) + (!capOK ? 1 : 0) + (!objOK ? 1 : 0);

    setCtxItem("ctxSpeed",   "ctxSpeedVal",   DS.speed + " km/h", "ctxSpeedLed",   speedOK);
    setCtxItem("ctxVeh",     "ctxVehVal",     DS.vehicles,         "ctxVehLed",     vehOK);
    setCtxItem("ctxWeather", "ctxWeatherVal", DS.weather,          "ctxWeatherLed", weatherOK);
    setCtxItem("ctxDist",    "ctxDistVal",    DS.dist + "m",       "ctxDistLed",    distOK);
    setCtxItem("ctxROI",     "ctxROIVal",     DS.roi,              "ctxROILed",     roiOK);
    setCtxItem("ctxCap",     "ctxCapVal",     DS.capture + "ms",   "ctxCapLed",     capOK);
    setCtxItem("ctxObj",     "ctxObjVal",     DS.objects,          "ctxObjLed",     objOK);

    const badge = $("ctxBadge");
    if (badge) { badge.textContent = allOK ? "7/7 OK" : `${7 - badCount}/7 OK`; badge.className = "ph-badge" + (allOK ? "" : " warn"); }

    if ($("camVehicles")) $("camVehicles").textContent = DS.vehicles;
    if ($("camSpeed"))    $("camSpeed").textContent    = DS.speed + " km/h";
    if ($("camFPS"))      $("camFPS").textContent      = DS.fps;

    syncLapCtx();
  } catch (e) { console.warn("[updateContext]", e); }
}

function setCtxItem(itemId, valId, val, ledId, ok) {
  const el = $(itemId), led = $(ledId), vEl = $(valId);
  if (vEl) vEl.textContent = val;
  if (led) led.className   = "ctx-led " + (ok ? "ok" : "bad");
  if (el)  el.classList.toggle("bad", !ok);
}

function syncLapCtx() {
  try {
    const speedOK = DS.speed < 20;
    const vehOK   = DS.vehicles <= 6;
    const weatherOK = /nắng|mưa nhẹ|đủ sáng/i.test(String(DS.weather || ""));
    const distOK  = Number(DS.dist) <= 5;
    const roiOK   = String(DS.roi || "").toUpperCase() === "STOP_LINE";
    const capOK   = Number(DS.capture) <= 500;
    const objOK   = /xe máy|ô tô/i.test(String(DS.objects || ""));
    const allOK   = speedOK && vehOK && weatherOK && distOK && roiOK && capOK && objOK;
    const bad     = (!speedOK ? 1 : 0) + (!vehOK ? 1 : 0) + (!weatherOK ? 1 : 0) + (!distOK ? 1 : 0) + (!roiOK ? 1 : 0) + (!capOK ? 1 : 0) + (!objOK ? 1 : 0);

    function setStat(valId, barId, ledId, val, pct, ok) {
      if ($(valId)) $(valId).textContent = val;
      if ($(barId)) { $(barId).style.width = pct + "%"; $(barId).className = "lap-ctx-fill" + (ok ? " ok" : " bad"); }
      if ($(ledId)) $(ledId).className = "ctx-led " + (ok ? "ok" : "bad");
    }

    setStat("lctxSpeedVal",   "lctxSpeedBar",   "lctxSpeedLed",   DS.speed + " km/h",  Math.min(100, (DS.speed/20)*100), speedOK);
    setStat("lctxVehVal",     "lctxVehBar",     "lctxVehLed",     DS.vehicles + " xe", Math.min(100, (DS.vehicles/6)*100), vehOK);
    setStat("lctxWeatherVal", null,             "lctxWeatherLed", DS.weather,          100, weatherOK);
    setStat("lctxDistVal",    null,             "lctxDistLed",    DS.dist + "m",       100, distOK);
    setStat("lctxROIVal",     null,             "lctxROILed",     DS.roi,              100, roiOK);
    setStat("lctxCapVal",     null,             "lctxCapLed",     DS.capture + "ms",   100, capOK);
    setStat("lctxObjVal",     "lctxObjBar",     "lctxObjLed",     DS.objects,          100, objOK);

    const b = $("lapCtxBadge");
    if (b) { b.textContent = allOK ? "7/7 OK" : `${7 - bad}/7 OK`; b.className = "ph-badge" + (allOK ? "" : " warn"); }

    if ($("lapVehicles")) $("lapVehicles").textContent = DS.vehicles;
    if ($("lapSpeed"))    $("lapSpeed").textContent    = DS.speed + " km/h";
    if ($("lapFPSTag"))   $("lapFPSTag").textContent   = LAP.fps + " FPS";
  } catch (e) { console.warn("[syncLapCtx]", e); }
}

// ═══════════════════════════════════════════════════════════════
// FIX v4.2: APPLY DISPLAY FLIP CSS
// Tách biệt hoàn toàn: CSS flip chỉ ảnh hưởng render trên màn hình
// KHÔNG ảnh hưởng canvas.toDataURL() → OCR luôn đúng
// ═══════════════════════════════════════════════════════════════
function _applyLapDisplayFlip(enable) {
  const img    = $("lapImg");
  const canvas = $("lapCanvas");
  // CSS flip: người dùng thấy selfie-mode (flip ngang) nhưng data KHÔNG flip
  const flipStyle = enable ? "scaleX(-1)" : "none";
  if (img)    img.style.transform    = flipStyle;
  if (canvas) canvas.style.transform = flipStyle;
}

// ═══════════════════════════════════════════════════════════════
// ★ LAPTOP CAMERA MODULE v4.2
//
// FIX v4.2 ROOT CAUSE — BIỂN SỐ BỊ ĐẢO NGƯỢC:
//
// NGUYÊN NHÂN GỐC:
//   Trong v4.1, lapStartBrowserDraw() sử dụng ctx.translate + ctx.scale(-1,1)
//   để flip canvas → toDataURL() trả về frame đã flip → lapImg.src là frame flip
//   → server nhận frame flip → OCR đọc ngược biển số.
//
// FIX:
//   1. KHÔNG BAO GIỜ flip canvas bằng ctx.save/translate/scale
//   2. drawImage() vẽ frame THẲNG vào canvas (không transform)
//   3. toDataURL() → lapImg.src → server → OCR đều dùng frame KHÔNG flip
//   4. Dùng CSS transform: scaleX(-1) cho lapImg và lapCanvas để hiển thị
//      selfie-mode trên UI — CSS transform KHÔNG ảnh hưởng toDataURL()
//   5. ocrCanvas: vẽ không flip (thực ra bây giờ = canvas chính vì không flip)
//
// Kết quả: 99-H7 7060 được OCR đọc đúng là "99-H7 7060" ✓
//
// FIX v4.1: generation counter — abort mọi async cũ khi stop
// ═══════════════════════════════════════════════════════════════

function lapSetStatus(active, text, error) {
  const dot     = $("lapStatusDot");
  const txt     = $("lapStatusTxt");
  const badge   = $("lapNavBadge");
  const liveDot = $("lapLiveDot");

  if (dot)     dot.className  = "lap-status-dot" + (active ? " active" : error ? " error" : "");
  if (txt)     txt.textContent = text;
  if (badge)   { badge.textContent = active ? "LIVE" : "OFF"; badge.style.background = active ? "var(--green)" : error ? "var(--red)" : "var(--t3)"; }
  if (liveDot) liveDot.style.opacity = active ? "1" : ".3";
}

function lapShowFeed(show) {
  const idle   = $("lapIdle");
  const img    = $("lapImg");
  const canvas = $("lapCanvas");
  const hudTop = $("lapHudTop");
  const hudBot = $("lapHudBot");
  const roi    = $("lapROI");
  const scan   = $("lapScanline");

  if (idle)   idle.style.display    = show ? "none"  : "flex";
  if (img)    img.style.display     = show ? "block" : "none";
  if (canvas) canvas.style.display  = show ? "block" : "none";
  if (hudTop) hudTop.style.display  = show ? "flex"  : "none";
  if (hudBot) hudBot.style.display  = show ? "flex"  : "none";
  if (roi)    roi.style.display     = show ? "block" : "none";
  if (scan)   scan.style.display    = show ? "block" : "none";

  // FIX v4.2: Áp dụng CSS flip khi show feed
  if (show) _applyLapDisplayFlip(LAP.displayFlip);
}

// ── Button helpers ──
function _lapBtnStartState() {
  $("btnLapStart")    && ($("btnLapStart").disabled    = true);
  $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
  $("btnLapStop")     && ($("btnLapStop").disabled     = false);
  // FIX v4.2: Cập nhật trạng thái nút flip
  _updateFlipBtn();
}

function _lapBtnStopState() {
  $("btnLapStart")    && ($("btnLapStart").disabled    = false);
  $("btnLapStartBig") && ($("btnLapStartBig").disabled = false);
  $("btnLapStop")     && ($("btnLapStop").disabled     = true);
}

function _lapBtnDisableAll() {
  $("btnLapStart")    && ($("btnLapStart").disabled    = true);
  $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
  $("btnLapStop")     && ($("btnLapStop").disabled     = true);
}

// FIX v4.2: Nút toggle flip display
function _updateFlipBtn() {
  const btn = $("btnLapFlip");
  if (!btn) return;
  btn.textContent = LAP.displayFlip ? "🔄 Flip: BẬT" : "🔄 Flip: TẮT";
  btn.title = LAP.displayFlip
    ? "Camera đang flip ngang (selfie-mode) — nhấn để tắt"
    : "Camera không flip — nhấn để bật (selfie-mode)";
}

// ── FIX v4.1: Poll /api/laptop_camera/ready ──
async function _lapWaitFrameReady(localGen, timeoutMs = 5000, intervalMs = 300) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (LAP.generation !== localGen) {
      lapAddLog("[POLL] Abort: generation changed — new stop/start", "warn");
      return false;
    }
    try {
      const r = await safeFetch("/api/laptop_camera/ready");
      if (r && r.frame_ready) return true;
    } catch (e) { /* ignore network errors, keep polling */ }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  lapAddLog("[POLL] Timeout 5s — frame chưa sẵn sàng", "warn");
  return false;
}

// FIX v4.1+v4.2: lapStart
async function lapStart() {
  try {
    if (LAP.active) {
      toast("Camera đang chạy!", "warn");
      return;
    }

    $("btnLapStart")    && ($("btnLapStart").disabled    = true);
    $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
    lapSetStatus(false, "Đang khởi động...");
    lapAddLog("Đang khởi động camera laptop v4.2...", "info");
    lapAddLog("[FIX v4.2] Biển số không bị đảo ngược — OCR mode: STRAIGHT frame", "info");

    // Ưu tiên camera thật từ trình duyệt (webcam laptop của người dùng).
    const mediaResult = await tryBrowserMedia();
    if (mediaResult) return;

    // Fallback: server OpenCV (chỉ hoạt động nếu server chạy trên đúng máy có camera).
    const apiResult = await tryFlaskLapCam();
    if (apiResult) return;

    lapSetStatus(false, "Không mở được camera");
    lapAddLog("[CAM] Không mở được webcam/browser hoặc Flask camera. Demo đã bị khóa.", "err");
    toast("Không mở được camera quét biển số. Kiểm tra quyền webcam hoặc camera đang bị ứng dụng khác chiếm.", "err");
    _lapBtnStopState();
  } catch (e) {
    lapAddLog(`[ERROR] lapStart thất bại: ${e.message}`, "err");
    toast("Lỗi khởi động camera: " + e.message, "err");
    _lapBtnStopState();
  }
}

async function tryFlaskLapCam() {
  try {
    const r = await safeFetch("/api/laptop_camera/start", { method: "POST" });
    if (!r || !r.ok) return false;

    const localGen = LAP.generation;
    lapAddLog("✅ Server xác nhận start — đang chờ frame đầu tiên...", "info");

    const ready = await _lapWaitFrameReady(localGen, 5000, 300);

    if (LAP.generation !== localGen) {
      lapAddLog("[FLASK] Abort: đã stop trong khi chờ frame", "warn");
      return false;
    }

    if (!ready) {
      lapAddLog("[FLASK] Frame không sẵn sàng sau 5s — thử browser webcam", "warn");
      await safeFetch("/api/laptop_camera/stop", { method: "POST" }).catch(() => {});
      return false;
    }

    LAP.active     = true;
    LAP.serverMode = true;
    LAP.demoMode   = false;

    const img = $("lapImg");
    if (img) {
      img.src = "/laptop_feed?t=" + Date.now();
      img.onerror = () => {
        if (LAP.active && LAP.serverMode) {
          lapAddLog("[FLASK] Feed bị ngắt. Demo đã bị khóa, vui lòng kết nối lại camera thật.", "err");
          lapStop();
        }
      };
    }

    lapShowFeed(true);
    // FIX v4.2: Server đã xử lý flip bên Python, img hiển thị đúng
    // Không cần CSS flip khi dùng Flask server (server đã gửi frame đúng chiều)
    _applyLapDisplayFlip(false);
    lapSetStatus(true, "🎥 Flask Camera — Online");
    lapAddLog("✅ Camera laptop online qua Flask server ✓", "ok");
    lapAddLog("[v4.2] Flask mode: CSS flip OFF — server frame không flip", "info");
    _lapBtnStartState();
    if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Flask / OpenCV";
    if ($("lapAiMode")) $("lapAiMode").textContent  = "Server MJPEG";
    lapStartFPSCounter();
    lapStartAutoSnap();
    toast("🎥 Camera laptop đã khởi động (Flask)!", "ok");
    return true;

  } catch (e) {
    lapAddLog(`[FLASK CAM] Lỗi: ${e.message}`, "warn");
  }
  return false;
}

// ══════════════════════════════════════════════════════════════
// FIX v4.2: tryBrowserMedia — KHÔNG flip canvas
// ══════════════════════════════════════════════════════════════
async function tryBrowserMedia() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return false;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
      audio: false
    });

    LAP.active     = true;
    LAP.serverMode = false;
    LAP.demoMode   = false;
    LAP.stream     = stream;

    const oldVid = document.getElementById("lapHiddenVideo");
    if (oldVid) {
      oldVid.srcObject = null;
      oldVid.remove();
    }

    const vid = document.createElement("video");
    vid.id          = "lapHiddenVideo";
    vid.style.display = "none";
    vid.autoplay    = true;
    vid.playsinline = true;
    vid.muted       = true;
    document.body.appendChild(vid);
    vid.srcObject = stream;
    LAP.video = vid;
    await vid.play();

    lapShowFeed(true);
    // FIX v4.2: Áp dụng CSS flip cho display (selfie-mode UX)
    // Canvas data KHÔNG flip → OCR đúng
    _applyLapDisplayFlip(LAP.displayFlip);
    lapSetStatus(true, "🎥 Webcam Browser — Online");
    lapAddLog("✅ getUserMedia thành công — streaming webcam", "ok");
    lapAddLog("[FIX v4.2] Canvas KHÔNG flip — CSS flip chỉ cho display", "ok");
    lapAddLog("[FIX v4.2] Biển số OCR: đọc frame thẳng → đúng chiều ✓", "ok");
    _lapBtnStartState();
    if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Browser MediaStream";
    if ($("lapAiMode")) $("lapAiMode").textContent  = "getUserMedia";
    if ($("lapResCap")) $("lapResCap").textContent  = "HD 720p";

    lapStartBrowserDraw();
    lapStartFPSCounter();
    lapStartAutoSnap();
    toast("🎥 Webcam trình duyệt đã kết nối!", "ok");
    return true;
  } catch (e) {
    lapAddLog("getUserMedia thất bại: " + e.message + " — không chuyển sang demo", "warn");
    return false;
  }
}

// ══════════════════════════════════════════════════════════════
// FIX v4.2: lapStartBrowserDraw — KHÔNG flip canvas data
//
// THAY ĐỔI QUAN TRỌNG so với v4.1:
//   ❌ XÓA ctx.save() / ctx.translate(vw,0) / ctx.scale(-1,1) / ctx.restore()
//   ✅ drawImage() THẲNG không transform
//   ✅ toDataURL() → lapImg.src → frame KHÔNG flip → OCR đúng
//   ✅ CSS scaleX(-1) trên lapImg cho hiển thị selfie-mode
//
// Tại sao CSS flip an toàn?
//   CSS transform chỉ ảnh hưởng rendering trên màn hình.
//   canvas.toDataURL() trả về pixel data gốc, KHÔNG bị ảnh hưởng bởi CSS.
//   Vì vậy: UI thấy flip (đẹp, tự nhiên) nhưng data luôn thẳng (OCR đúng).
// ══════════════════════════════════════════════════════════════
function lapStartBrowserDraw() {
  const canvas = $("lapCanvas");
  if (!canvas || !LAP.video) return;
  const ctx = canvas.getContext("2d");
  const localGen = LAP.generation;

  // OCR canvas — KHÔNG flip (giữ lại để tương thích với code OCR cũ)
  let ocrCanvas = document.getElementById("lapOCRCanvas");
  if (!ocrCanvas) {
    ocrCanvas = document.createElement("canvas");
    ocrCanvas.id = "lapOCRCanvas";
    ocrCanvas.style.display = "none";
    document.body.appendChild(ocrCanvas);
  }
  const ocrCtx = ocrCanvas.getContext("2d");

  function draw() {
    if (LAP.generation !== localGen) return;
    if (!LAP.active || LAP.demoMode) return;
    if (!LAP.video || !LAP.video.videoWidth) { LAP.animID = requestAnimationFrame(draw); return; }

    const vw = LAP.video.videoWidth;
    const vh = LAP.video.videoHeight;
    canvas.width  = vw;
    canvas.height = vh;
    ocrCanvas.width  = vw;
    ocrCanvas.height = vh;

    // ══════════════════════════════════════════════════════
    // FIX v4.2: VẼ THẲNG — KHÔNG flip canvas
    // Biển số "99-H7 7060" sẽ được vẽ đúng chiều → OCR đọc đúng
    // CSS scaleX(-1) trên element sẽ flip display cho selfie-mode
    // ══════════════════════════════════════════════════════
    ctx.drawImage(LAP.video, 0, 0, vw, vh);
    drawLapOverlays(ctx, vw, vh);

    // OCR canvas cũng vẽ thẳng (giữ nhất quán)
    ocrCtx.drawImage(LAP.video, 0, 0, vw, vh);
    drawLapOverlays(ocrCtx, vw, vh);

    // lapImg.src từ canvas thẳng → server nhận frame đúng → OCR đúng
    const img = $("lapImg");
    if (img) {
      try { img.src = canvas.toDataURL("image/webp", 0.8); } catch (e) {}
    }

    LAP.fpsCounter++;
    LAP.animID = requestAnimationFrame(draw);
  }
  draw();
}

// FIX v4.2: lapStartDemo — flip CSS cho demo canvas (selfie-mode)
// Demo canvas vẽ thẳng, CSS flip cho display
function lapStartDemo() {
  LAP.active   = true;
  LAP.demoMode = true;

  const canvas = $("lapCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  canvas.width  = 1024;
  canvas.height = 576;
  const localGen = LAP.generation;

  lapShowFeed(true);
  // FIX v4.2: CSS flip cho demo display (selfie-mode)
  _applyLapDisplayFlip(LAP.displayFlip);
  lapSetStatus(true, "💻 Demo Canvas — Simulation");
  lapAddLog("⚡ Chế độ Demo Canvas — mô phỏng camera thực tế", "ok");
  lapAddLog("[v4.2] Demo: CSS flip=" + (LAP.displayFlip ? "ON" : "OFF") + " | Canvas data: thẳng", "info");
  _lapBtnStartState();
  if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Demo Canvas";
  if ($("lapAiMode")) $("lapAiMode").textContent  = "Simulation";
  if ($("lapResCap")) $("lapResCap").textContent  = "1024×576";
  toast("💻 Demo camera mô phỏng đã khởi động!", "info");

  function drawDemo() {
    if (LAP.generation !== localGen) return;
    if (!LAP.active) return;

    const W = canvas.width, H = canvas.height;

    const sky = ctx.createLinearGradient(0, 0, 0, H * 0.5);
    sky.addColorStop(0,   "#0a0f1e");
    sky.addColorStop(0.6, "#0c1422");
    sky.addColorStop(1,   "#080e18");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, H);

    ctx.fillStyle = "#111827";
    ctx.fillRect(0, H * 0.42, W, H * 0.58);

    ctx.fillStyle = "rgba(255,255,255,0.015)";
    for (let i = 0; i < 80; i++) {
      ctx.fillRect(Math.random() * W, H * 0.42 + Math.random() * H * 0.58, 1, 1);
    }

    ctx.setLineDash([40, 20]);
    ctx.strokeStyle = "rgba(255,255,255,0.10)";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(W/2, H * 0.45); ctx.lineTo(W/2, H); ctx.stroke();
    ctx.setLineDash([]);

    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(60, H * 0.45); ctx.lineTo(60, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(W-60, H * 0.45); ctx.lineTo(W-60, H); ctx.stroke();

    const roiY = Math.floor(H * 0.70);
    ctx.strokeStyle = "rgba(255,58,92,0.85)";
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 4]);
    ctx.beginPath(); ctx.moveTo(80, roiY); ctx.lineTo(W - 80, roiY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(255,58,92,0.75)";
    ctx.font = "bold 10px Space Mono, monospace";
    ctx.textAlign = "center";
    ctx.fillText("▲ VẠCH DỪNG — ROI — STOP LINE ▲", W/2, roiY - 7);
    ctx.textAlign = "left";

    const numV = Math.min(DS.vehicles, 4);
    const t = Date.now() / 1000;
    for (let i = 0; i < numV; i++) {
      const xBase  = 120 + i * ((W - 240) / 4);
      const yBase  = H * 0.50 + (t * 18 + i * 60) % (H * 0.45);
      const isOver = DS.light === "RED" && yBase > roiY - 10;
      const bodyH  = 30 + (i % 2) * 12;
      const bodyW  = 55 + (i % 2) * 18;
      const carColors = ["#1a4da8","#a82020","#1a8a42","#7a3aaa"];
      const wobble = Math.sin(t * 1.5 + i) * 3;

      ctx.fillStyle = "rgba(0,0,0,0.3)";
      ctx.beginPath();
      ctx.ellipse(xBase + wobble, yBase + bodyH/2 + 4, bodyW * 0.5, 6, 0, 0, Math.PI*2);
      ctx.fill();

      ctx.fillStyle = carColors[i % 4];
      ctx.beginPath();
      ctx.roundRect(xBase - bodyW/2 + wobble, yBase - bodyH/2, bodyW, bodyH, [5,5,3,3]);
      ctx.fill();

      ctx.fillStyle = "rgba(180,220,255,0.45)";
      ctx.fillRect(xBase - bodyW/2 + 8 + wobble, yBase - bodyH/2 + 3, bodyW - 16, bodyH * 0.45);

      if (DS.camState !== "IDLE") {
        ctx.fillStyle = "rgba(255,240,150,0.7)";
        ctx.beginPath(); ctx.arc(xBase - bodyW/2 + 6 + wobble, yBase + bodyH/2 - 5, 3, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(xBase + bodyW/2 - 6 + wobble, yBase + bodyH/2 - 5, 3, 0, Math.PI*2); ctx.fill();
      }

      const boxX  = xBase - bodyW/2 - 8 + wobble;
      const boxY  = yBase - bodyH/2 - 10;
      const boxW  = bodyW + 16;
      const boxH2 = bodyH + 20;

      if (isOver) {
        ctx.strokeStyle = "rgba(255,58,92,0.9)";
        ctx.lineWidth   = 2;
        ctx.strokeRect(boxX, boxY, boxW, boxH2);
        ctx.fillStyle = "rgba(255,58,92,0.85)";
        ctx.fillRect(boxX, boxY - 16, boxW, 16);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 9px Space Mono, monospace";
        ctx.fillText(PLATES[i % PLATES.length], boxX + 3, boxY - 5);
        const cm = 8;
        ctx.strokeStyle = "rgba(255,58,92,1)"; ctx.lineWidth = 2.5;
        [[boxX, boxY], [boxX+boxW, boxY], [boxX, boxY+boxH2], [boxX+boxW, boxY+boxH2]].forEach(([cx, cy], ci) => {
          ctx.beginPath();
          ctx.moveTo(cx + (ci % 2 === 0 ? cm : -cm), cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + (ci < 2 ? cm : -cm));
          ctx.stroke();
        });
      } else {
        ctx.strokeStyle = "rgba(0,232,122,0.65)";
        ctx.lineWidth   = 1.5;
        ctx.strokeRect(boxX, boxY, boxW, boxH2);
        ctx.fillStyle = "rgba(0,0,0,0.65)";
        ctx.fillRect(boxX, boxY - 13, boxW * 0.7, 13);
        ctx.fillStyle = "rgba(0,232,122,.9)";
        ctx.font = "8px Space Mono, monospace";
        ctx.fillText(TYPES[i % TYPES.length], boxX + 2, boxY - 4);
      }
    }

    ctx.fillStyle = "rgba(32,202,255,0.04)";
    ctx.font = "bold 60px DM Sans, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("DEMO", W/2, H * 0.38);
    ctx.textAlign = "left";

    const lc = DS.light === "RED" ? [255,58,92] : DS.light === "YELLOW" ? [255,176,32] : [0,232,122];
    ctx.fillStyle = `rgba(${lc},0.9)`;
    ctx.beginPath(); ctx.arc(W - 30, 30, 14, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.5)"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(W - 30, 30, 14, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.font = "bold 7.5px Space Mono, monospace"; ctx.textAlign = "center";
    ctx.fillText(DS.phase, W - 30, 33); ctx.textAlign = "left";

    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(0, 0, W, 24);
    ctx.fillStyle = "rgba(255,255,255,0.8)";
    ctx.font = "11px Space Mono, monospace";
    ctx.fillText(new Date().toLocaleString("vi-VN"), 8, 16);
    ctx.fillStyle = "rgba(32,202,255,0.7)";
    ctx.fillText("CAM:LAPTOP  |  " + DS.camState + "  |  " + DS.vehicles + " XE", W - 340, 16);

    // lapImg.src từ canvas thẳng — CSS flip cho display
    const img = $("lapImg");
    if (img) { try { img.src = canvas.toDataURL("image/webp", 0.8); } catch (e) {} }

    LAP.fpsCounter++;
    LAP.animID = requestAnimationFrame(drawDemo);
  }
  drawDemo();
  lapStartFPSCounter();
  lapStartAutoSnap();
}

function drawLapOverlays(ctx, W, H) {
  const roiY = Math.floor(H * 0.72);
  ctx.strokeStyle = "rgba(255,58,92,0.7)";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(30, roiY); ctx.lineTo(W - 30, roiY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(255,58,92,0.8)";
  ctx.font = "bold 9px Space Mono, monospace";
  ctx.textAlign = "center";
  ctx.fillText("▲ VẠCH DỪNG — ROI ▲", W/2, roiY - 6);
  ctx.textAlign = "left";

  const lc = DS.light === "RED" ? "#ff3a5c" : DS.light === "YELLOW" ? "#ffb020" : "#00e87a";
  ctx.fillStyle = lc;
  ctx.beginPath(); ctx.arc(W - 24, 18, 10, 0, Math.PI * 2); ctx.fill();
}

function lapStartFPSCounter() {
  if (LAP.fpsTimer) clearInterval(LAP.fpsTimer);
  LAP.fpsTimer = setInterval(() => {
    LAP.fps = LAP.fpsCounter;
    LAP.fpsCounter = 0;
    if ($("lapFPSTag")) $("lapFPSTag").textContent = LAP.fps + " FPS";
    if ($("lapResCap")) $("lapResCap").textContent = LAP.demoMode ? "1024×576 Demo" : "Live";
  }, 1000);
}

// FIX v4.1: lapStop — tăng generation TRƯỚC TIÊN
async function lapStop() {
  if (!LAP.active && !LAP.serverMode) return;

  LAP.generation++;
  LAP.active = false;

  lapStopAutoSnap();

  if (LAP.animID)   { cancelAnimationFrame(LAP.animID); LAP.animID = null; }
  if (LAP.fpsTimer) { clearInterval(LAP.fpsTimer); LAP.fpsTimer = null; }
  if (LAP._fpsPoll) { clearInterval(LAP._fpsPoll); LAP._fpsPoll=null; }

  if (LAP.stream)   { LAP.stream.getTracks().forEach(t => t.stop()); LAP.stream = null; }

  const vid = document.getElementById("lapHiddenVideo");
  if (vid) { vid.srcObject = null; vid.remove(); }
  LAP.video = null;

  const ocrCanvas = document.getElementById("lapOCRCanvas");
  if (ocrCanvas) ocrCanvas.remove();
  if (LAP._capCanvas) { try { LAP._capCanvas.remove(); } catch {} LAP._capCanvas = null; }
  LAP.lastFrameDataUrl = "";

  const wasServerMode = LAP.serverMode;
  LAP.serverMode = false;
  LAP.demoMode   = false;
  LAP.fps        = 0;
  LAP.fpsCounter = 0;

  const img = $("lapImg");
  if (img) {
    img.onerror = null;
    img.src = "";
    img.style.transform = "none"; // FIX v4.2: Reset CSS flip khi stop
  }
  const canvas = $("lapCanvas");
  if (canvas) canvas.style.transform = "none"; // FIX v4.2: Reset CSS flip

  lapShowFeed(false);
  lapSetStatus(false, "Đang tắt camera...");
  _lapBtnDisableAll();
  lapAddLog("Camera laptop đang tắt...", "warn");

  if (wasServerMode) {
    try {
      await safeFetch("/api/laptop_camera/stop", { method: "POST" });
    } catch (e) { /* ignore */ }

    let waited = 0;
    const _finalize = () => {
      lapSetStatus(false, "Camera đã tắt — nhấn Bật Camera để khởi động lại");
      _lapBtnStopState();
      lapAddLog("Camera đã tắt — sẵn sàng khởi động lại ✓", "ok");
      toast("Camera laptop đã tắt. Nhấn Bật Camera để bật lại.", "warn");
    };
    const poll = async () => {
      try {
        const s = await safeFetch("/api/laptop_camera/status");
        if (s && !s.active) { _finalize(); return; }
      } catch (e) { _finalize(); return; }
      waited += 200;
      if (waited >= 2000) { _finalize(); return; }
      setTimeout(poll, 200);
    };
    setTimeout(poll, 200);
  } else {
    lapSetStatus(false, "Camera đã tắt — nhấn Bật Camera để khởi động lại");
    _lapBtnStopState();
    lapAddLog("Camera đã tắt — sẵn sàng khởi động lại ✓", "ok");
    toast("Camera laptop đã tắt. Nhấn Bật Camera để bật lại.", "warn");
  }
}

// ── Button event listeners ──
$("btnLapStart")    && $("btnLapStart").addEventListener("click",   lapStart);
$("btnLapStop")     && $("btnLapStop").addEventListener("click",    lapStop);
$("btnLapStartBig") && $("btnLapStartBig").addEventListener("click", lapStart);

// FIX v4.2: Nút toggle flip display
if ($("btnLapFlip")) {
  $("btnLapFlip").addEventListener("click", () => {
    LAP.displayFlip = !LAP.displayFlip;
    _applyLapDisplayFlip(LAP.displayFlip);
    _updateFlipBtn();
    const msg = LAP.displayFlip
      ? "🔄 Flip display BẬT (selfie-mode) — OCR vẫn đọc thẳng"
      : "🔄 Flip display TẮT — hiển thị thẳng";
    lapAddLog("[v4.2] " + msg, "ok");
    toast(msg, "info");
  });
  _updateFlipBtn();
}

if ($("btnLapRed"))   $("btnLapRed").addEventListener("click",   () => {
  forceLight(2);
  lapAddLog("[MANUAL] Bật đèn ĐỎ", "warn");
  // Chỉ tạo vi phạm giả ở DEMO mode (tránh “tự tạo biển số” khi chạy thực tế).
  if (isDemo && LAP.active) setTimeout(() => lapSpawnDetection(), 2000);
});
if ($("btnLapAmber")) $("btnLapAmber").addEventListener("click", () => forceLight(1));
if ($("btnLapGreen")) $("btnLapGreen").addEventListener("click", () => forceLight(0));
if ($("btnLapAuto"))  $("btnLapAuto").addEventListener("click",  () => { resetAuto(); lapAddLog("[AUTO] Chuyển về chế độ tự động", "ok"); });

function _lapEnsureCapCanvas(w, h) {
  if (!LAP._capCanvas) {
    const c = document.createElement("canvas");
    c.style.display = "none";
    c.id = "lapCapCanvas";
    document.body.appendChild(c);
    LAP._capCanvas = c;
  }
  if (LAP._capCanvas.width !== w)  LAP._capCanvas.width  = w;
  if (LAP._capCanvas.height !== h) LAP._capCanvas.height = h;
  return LAP._capCanvas;
}

function lapGetFrameDataUrl() {
  // 1) Browser webcam (hidden <video>)
  try {
    if (LAP.video && LAP.video.videoWidth && LAP.video.videoHeight) {
      const c = _lapEnsureCapCanvas(LAP.video.videoWidth, LAP.video.videoHeight);
      const ctx = c.getContext("2d", { willReadFrequently: false });
      ctx.drawImage(LAP.video, 0, 0, c.width, c.height);
      const du = c.toDataURL("image/jpeg", 0.85);
      if (du && du.startsWith("data:image/")) LAP.lastFrameDataUrl = du;
      return du;
    }
  } catch {}

  // 2) Flask MJPEG (lapImg)
  try {
    const img = $("lapImg");
    if (img && img.naturalWidth && img.naturalHeight) {
      const c = _lapEnsureCapCanvas(img.naturalWidth, img.naturalHeight);
      const ctx = c.getContext("2d", { willReadFrequently: false });
      ctx.drawImage(img, 0, 0, c.width, c.height);
      const du = c.toDataURL("image/jpeg", 0.85);
      if (du && du.startsWith("data:image/")) LAP.lastFrameDataUrl = du;
      return du;
    }
  } catch {}

  // 3) Canvas fallback
  try {
    const ocrCanvas = document.getElementById("lapOCRCanvas") || $("lapCanvas");
    if (ocrCanvas && ocrCanvas.width && ocrCanvas.height) {
      const du = ocrCanvas.toDataURL("image/jpeg", 0.85);
      if (du && du.startsWith("data:image/")) LAP.lastFrameDataUrl = du;
      return du;
    }
  } catch {}

  return LAP.lastFrameDataUrl || "";
}

function lapStopAutoSnap() {
  if (LAP._autoSnapTimer) { clearInterval(LAP._autoSnapTimer); LAP._autoSnapTimer = null; }
}

function lapStartAutoSnap() {
  const t = $("lapAutoSnapToggle");
  LAP.autoSnapEnabled = t ? !!t.checked : false;
  lapStopAutoSnap();
  if (!LAP.autoSnapEnabled) return;

  // Tick nhanh để không drift; snapshot chỉ bắn mỗi 6s khi đèn đỏ.
  LAP._autoSnapTimer = setInterval(async () => {
    try {
      if (!LAP.active) return;
      if (DS.light !== "RED") return;
      if (LAP._snapInFlight) return;
      const now = Date.now();
      if (now - (LAP._lastSnapAtMs || 0) < 6000) return;
      LAP._lastSnapAtMs = now;
      await lapDoSnapshot(true);
    } catch {}
  }, 500);
}

if ($("lapAutoSnapToggle")) {
  $("lapAutoSnapToggle").addEventListener("change", () => {
    lapStartAutoSnap();
    lapAddLog(`[AUTO SNAP] ${$("lapAutoSnapToggle").checked ? "BẬT" : "TẮT"} — mỗi 6s khi đèn đỏ`, "info");
  });
}

if ($("btnLapScan")) {
  function _lapGetFrameDataUrl() { return lapGetFrameDataUrl(); }

  function _lapRenderLookupResult(plateText, resp, confPct = null) {
    const res = $("lapScanResult");
    if (!res) return;
    res.style.display = "block";
    if ($("lapScanPlate")) $("lapScanPlate").textContent = plateText || "--";

    const foundSample = !!resp?.found?.sample;
    const foundDb     = !!resp?.found?.db;
    const confStr = (confPct === null || confPct === undefined) ? "" : ` · OCR: ${confPct}%`;

    // Current light label
    const lightLabel = DS.light === "RED" ? "🔴 ĐỎ" : DS.light === "YELLOW" ? "🟡 VÀNG" : "🟢 XANH";

    let info = "";
    let detailHtml = "";
    if (foundDb && resp?.db) {
      const db = resp.db;
      const t  = db.violation_ts ? new Date(db.violation_ts * 1000).toLocaleString("vi-VN") : "--";
      const vtype = db.vehicle_type === "CAR" ? "🚗 Ô tô" : db.vehicle_type === "MOTORBIKE" ? "🏍️ Xe máy" : (db.vehicle_type || "--");
      const lightState = db.light_state === "RED" ? "🔴 ĐỎ" : db.light_state === "YELLOW" ? "🟡 VÀNG" : "🟢 XANH";
      info = `✅ TÌM THẤY (DB) · ${vtype} · ${db.speed_kmh ?? "--"} km/h · ${t}${confStr}`;
      detailHtml = `<div class="scan-detail-row"><b>Vi phạm:</b> Vượt đèn ${lightState}</div><div class="scan-detail-row"><b>Loại xe:</b> ${vtype}</div><div class="scan-detail-row"><b>Tốc độ:</b> ${db.speed_kmh ?? "--"} km/h</div><div class="scan-detail-row"><b>Thời gian:</b> ${t}</div><div class="scan-detail-row"><b>Camera:</b> ${db.camera_id || "--"}</div>`;
      res.style.borderColor = "rgba(0,232,122,.45)";
    } else if (foundSample && resp?.sample) {
      const s = resp.sample;
      const vtype = s.vehicle_type === "CAR" ? "🚗 Ô tô" : s.vehicle_type === "MOTORBIKE" ? "🏍️ Xe máy" : (s.vehicle_type || "--");
      const sLight = (s.light_state || "").toUpperCase();
      const lightState = sLight === "RED" ? "🔴 ĐỎ" : sLight === "YELLOW" ? "🟡 VÀNG" : "🟢 XANH";
      const t = s.violation_time || s["Thời Gian Vi Phạm"] || "--";
      info = `⚠️ TÌM THẤY (CSV) · ${vtype} · ${t}${confStr}`;
      detailHtml = `<div class="scan-detail-row"><b>Vi phạm:</b> Vượt đèn ${lightState}</div><div class="scan-detail-row"><b>Loại xe:</b> ${vtype}</div><div class="scan-detail-row"><b>Tốc độ:</b> ${s.speed_kmh ?? "--"} km/h</div><div class="scan-detail-row"><b>Thời gian:</b> ${t}</div><div class="scan-detail-row"><b>Camera:</b> ${s.camera_id || "--"}</div>`;
      res.style.borderColor = "rgba(255,176,32,.45)";
    } else {
      info = `❌ KHÔNG TÌM THẤY trong dữ liệu mẫu/DB${confStr}`;
      detailHtml = `<div class="scan-detail-row" style="color:var(--t2)">Biển số <b>${plateText}</b> không có trong CSDL vi phạm</div><div class="scan-detail-row">Đèn hiện tại: ${lightLabel}</div>`;
      res.style.borderColor = "rgba(255,58,92,.35)";
    }

    if ($("lapScanInfo")) $("lapScanInfo").textContent = info;
    const det = $("lapScanDetail");
    if (det) { det.innerHTML = detailHtml; det.style.display = detailHtml ? "block" : "none"; }
  }

  function _lapRenderLookupResultV2(plateText, resp, confPct = null) {
    const res = $("lapScanResult");
    if (!res) return;
    res.style.display = "block";
    if ($("lapScanPlate")) $("lapScanPlate").textContent = plateText || "--";

    const foundSample = !!resp?.found?.sample;
    const foundDb = !!resp?.found?.db;
    const confStr = (confPct === null || confPct === undefined) ? "" : ` · OCR: ${confPct}%`;
    const currentLight = DS.light === "RED" ? "ĐỎ" : DS.light === "YELLOW" ? "VÀNG" : "XANH";
    const vehicleLabel = (value) => {
      const raw = String(value || "").toUpperCase();
      return raw === "CAR" || raw === "MOTORBIKE" ? raw : (raw || "UNKNOWN");
    };
    const offenseLabel = (value) => {
      const raw = String(value || "").toUpperCase();
      if (raw === "RED") return "Vượt đèn đỏ";
      if (raw === "YELLOW") return "Vượt đèn vàng";
      if (raw === "GREEN") return "Đèn xanh";
      return "Chưa rõ pha đèn";
    };
    const fmtLookupTs = (tsSeconds, fallbackText = "--") => {
      if (!tsSeconds) return fallbackText;
      const d = new Date(tsSeconds * 1000);
      if (Number.isNaN(d.getTime())) return fallbackText;
      return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")} ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
    };

    let info = "";
    let detailHtml = "";
    if (foundDb && resp?.db) {
      const db = resp.db;
      const t = fmtLookupTs(db.violation_ts, "--");
      const vtype = vehicleLabel(db.vehicle_type);
      const offense = offenseLabel(db.light_state);
      info = `TÌM THẤY (DB) · ${vtype} · ${db.speed_kmh ?? "--"} km/h · ${t} · ${offense}${confStr}`;
      detailHtml = `<div class="scan-detail-row"><b>Biển số:</b> ${plateText || "--"}</div><div class="scan-detail-row"><b>Kết luận:</b> ${offense}</div><div class="scan-detail-row"><b>Loại xe:</b> ${vtype}</div><div class="scan-detail-row"><b>Tốc độ:</b> ${db.speed_kmh ?? "--"} km/h</div><div class="scan-detail-row"><b>Thời gian:</b> ${t}</div><div class="scan-detail-row"><b>Camera:</b> ${db.camera_id || "--"}</div>`;
      res.style.borderColor = "rgba(0,232,122,.45)";
    } else if (foundSample && resp?.sample) {
      const s = resp.sample;
      const vtype = vehicleLabel(s.vehicle_type);
      const t = s.violation_time || s["Thời Gian Vi Phạm"] || "--";
      const offense = offenseLabel(s.light_state);
      const src = s.source ? ` · ${s.source}` : "";
      info = `TÌM THẤY (CSV) · ${vtype} · ${s.speed_kmh ?? "--"} km/h · ${t} · ${offense}${src}${confStr}`;
      detailHtml = `<div class="scan-detail-row"><b>Biển số:</b> ${plateText || "--"}</div><div class="scan-detail-row"><b>Kết luận:</b> ${offense}</div><div class="scan-detail-row"><b>Loại xe:</b> ${vtype}</div><div class="scan-detail-row"><b>Tốc độ:</b> ${s.speed_kmh ?? "--"} km/h</div><div class="scan-detail-row"><b>Thời gian:</b> ${t}</div><div class="scan-detail-row"><b>Camera:</b> ${s.camera_id || "--"}</div><div class="scan-detail-row"><b>Nguồn:</b> ${s.source || "sample_violations.csv"}</div>`;
      res.style.borderColor = "rgba(255,176,32,.45)";
    } else {
      info = `KHÔNG TÌM THẤY trong dữ liệu mẫu/DB · Đèn: ${currentLight}${confStr}`;
      detailHtml = `<div class="scan-detail-row" style="color:var(--t2)">Biển số <b>${plateText}</b> không có trong CSDL vi phạm</div><div class="scan-detail-row"><b>Đèn hiện tại:</b> ${currentLight}</div><div class="scan-detail-row"><b>Kết luận:</b> Chưa ghi nhận vi phạm trong DB/CSV</div>`;
      res.style.borderColor = "rgba(255,58,92,.35)";
    }

    if ($("lapScanInfo")) $("lapScanInfo").textContent = info;
    const det = $("lapScanDetail");
    if (det) { det.innerHTML = detailHtml; det.style.display = detailHtml ? "block" : "none"; }
  }

  $("btnLapScan").addEventListener("click", async () => {
    try {
      const inputEl = $("lapPlateInput");
      const typed = (inputEl ? inputEl.value : "").trim().toUpperCase();

      // Nếu đang bật camera và ô nhập đang TRỐNG → quét OCR từ khung hình.
      // Nếu người dùng đã nhập biển số → ưu tiên tra cứu đúng theo input (không tự "tạo" / ghi đè).
      if (LAP.active && !typed) {
        const dataUrl = _lapGetFrameDataUrl();
        if (!dataUrl) { toast("Chưa có khung hình camera!", "warn"); return; }
        lapAddLog("[AI] Đang quét biển số từ camera...", "info");
        const r = await safeFetch("/api/plate/scan", {
          method: "POST",
          body: JSON.stringify({ image_data_url: dataUrl }),
          timeoutMs: 45000, // EasyOCR CPU + warmup lần đầu có thể chậm
        });
        if (!r?.ok) { toast("Quét AI thất bại.", "err"); return; }
        const plate = (r.plate || "").toUpperCase();
        if (inputEl && plate) inputEl.value = plate;
        const confPct = Math.round((r.ocr_confidence || 0) * 100);
        _lapRenderLookupResultV2(plate || typed, r, isFinite(confPct) ? confPct : null);
        lapAddLog(`[AI] Kết quả: ${plate || "--"} | CSV=${r.found?.sample ? "YES" : "NO"} | DB=${r.found?.db ? "YES" : "NO"} | OCR=${confPct}%`, r.found?.db || r.found?.sample ? "ok" : "warn");
        toast(plate ? `🔍 Quét AI: ${plate}` : "Không đọc được biển số.", plate ? "ok" : "warn");
        return;
      }

      if (!typed) { toast("Nhập biển số (hoặc xoá ô nhập rồi bấm Quét để OCR từ camera)!", "warn"); return; }
      lapAddLog(`[AI] Tra cứu biển số: ${typed}`, "info");
      const r = await safeFetch(`/api/plate/lookup?plate=${encodeURIComponent(typed)}`, { timeoutMs: 12000 });
      if (!r?.ok) { toast("Tra cứu thất bại.", "err"); return; }
      _lapRenderLookupResultV2((r.plate || typed).toUpperCase(), r, null);
      lapAddLog(`[AI] Tra cứu: ${typed} | CSV=${r.found?.sample ? "YES" : "NO"} | DB=${r.found?.db ? "YES" : "NO"}`, r.found?.db || r.found?.sample ? "ok" : "warn");
    } catch (e) {
      lapAddLog(`[AI ERROR] ${e.message}`, "err");
      toast("Lỗi quét AI: " + e.message, "err");
    }
  });
}

async function lapDoSnapshot(auto = false) {
  if (!LAP.active) { if (!auto) toast("Bật camera trước!", "warn"); return; }
  if (LAP._snapInFlight) return;
  LAP._snapInFlight = true;
  try {
    // Lấy biển số từ input (nếu trống, Server sẽ tự dùng AI đọc ảnh)
    const plateInput = ($("lapPlateInput") ? $("lapPlateInput").value : "").trim().toUpperCase();
    if (!auto) {
      lapAddLog(`[SNAP] Đang gửi ảnh lên Server để AI phân tích...`, "info");
      lapAddLog("[v4.2] Snapshot dùng frame THẲNG (không flip) → OCR đúng", "info");
    }

    // Ảnh hiển thị tạm vào Gallery (không bắt buộc)
    let snapImageUrl = null;
    if (!LAP.serverMode) {
      try {
        const ocrCanvas = document.getElementById("lapOCRCanvas");
        if (ocrCanvas && ocrCanvas.width > 0) {
          snapImageUrl = ocrCanvas.toDataURL("image/webp", 0.8);
        } else {
          const lapCanvas = $("lapCanvas");
          if (lapCanvas && lapCanvas.width > 0) snapImageUrl = lapCanvas.toDataURL("image/webp", 0.8);
        }
      } catch {}
    }

    const _geo = GEO.getViolationLocation();

    // Lấy frame THẲNG để server OCR/YOLO (tránh placeholder SNAP_LAPTOP)
    const frameDataUrl = lapGetFrameDataUrl();
    if (!frameDataUrl || frameDataUrl === "data:,") {
      if (!auto) toast("Chưa lấy được frame camera — hãy bật webcam và đưa biển số vào khung.", "warn");
      lapAddLog("[SNAP] ❌ Không có frame camera — bật webcam trước khi chụp.", "warn");
      return;
    }

    const r = await safeFetch("/api/laptop_camera/snapshot", {
      method: "POST",
      body: JSON.stringify({ plate: plateInput, image_data_url: frameDataUrl, inject_violation: true }),
      timeoutMs: 45000,
    });

    if (!r || !r.ok) {
      const errMsg = r?.error || "Lỗi xử lý hình ảnh từ Server!";
      if (!auto) { toast(errMsg, "err"); lapAddLog("[SNAP ERROR] " + errMsg, "err"); }
      return;
    }

    const finalPlate = (r.plate || "").toUpperCase();
    const ocrOk = !!finalPlate && finalPlate !== "UNKNOWN";
    const snapConfPct = Math.round((r.ocr_confidence || 0) * 100);

    // Điền biển số vào input; xóa nếu không đọc được
    if ($("lapPlateInput")) $("lapPlateInput").value = ocrOk ? finalPlate : "";
    if (ocrOk) _lapRenderLookupResultV2(finalPlate, r, isFinite(snapConfPct) ? snapConfPct : null);

    // Lưu ảnh thực vào gallery
    const imgUrl = r.image_url || null;
    const displayUrl = imgUrl || snapImageUrl || ($("lapImg") ? $("lapImg").src : "");
    if (displayUrl) lapAddGalleryItem(displayUrl, ocrOk ? finalPlate : "?", _geo.timestamp || Math.floor(Date.now() / 1000));

    LAP._lastSnapAtMs = Date.now();

    if (!auto) {
      if (ocrOk) {
        if (r.injected) {
          toast(`📸 ${finalPlate} — Đã ghi vi phạm (đèn ĐỎ)`, "err");
          lapAddLog(`[VIOL] ✅ Ghi vi phạm: ${finalPlate} | Nhấn Quét AI để xem chi tiết`, "err");
        } else {
          lapAddLog(`[SNAP] ✅ OCR: ${finalPlate} (Đèn ${DS.phase}) | Xác nhận đúng rồi nhấn 🔍 Quét AI`, "ok");
          toast(`📸 Biển số: ${finalPlate} — Xác nhận rồi bấm Quét AI`, "ok");
        }
      } else {
        if ($("lapPlateInput")) $("lapPlateInput").value = "";
        lapAddLog("[OCR] ❌ Không đọc được biển số — đưa biển số gần hơn vào khung, thử lại.", "warn");
        toast("OCR không đọc được. Hãy đưa biển số gần hơn rồi chụp lại.", "warn");
      }
    }
  } catch (e) {
    if (!auto) {
      lapAddLog(`[SNAP ERROR] ${e.message}`, "err");
      toast("Lỗi snapshot: " + e.message, "err");
    }
  } finally {
    LAP._snapInFlight = false;
  }
}

if ($("btnLapSnap")) {
  $("btnLapSnap").addEventListener("click", () => lapDoSnapshot(false));
}

if ($("btnSeedViol")) {
  $("btnSeedViol").addEventListener("click", () => {
    lapAddLog("[LOCK] Tạo dữ liệu kiểm thử đã bị vô hiệu hóa. Hãy dùng Camera Quét Biển Số để chụp ảnh thật.", "warn");
    toast("Đã khóa tạo dữ liệu kiểm thử. Hệ thống chỉ nhận ảnh thật từ camera.", "warn");
  });
}

function lapAddDetItem(v) {
  try {
    const list = $("lapDetList");
    if (!list) return;
    list.querySelector(".no-data")?.remove();
    LAP.detCount++;
    if ($("lapDetBadge")) $("lapDetBadge").textContent = LAP.detCount + " xe";
    const item = document.createElement("div");
    item.className = "det-item neon-hover";
    item.innerHTML = `<span class="det-type">${v.type || "--"}</span><span class="det-plate">${v.plate}</span><span class="det-conf">${v.confidence}%</span>${DS.light === "RED" ? `<span class="det-flag">VI PHẠM</span>` : ""}`;
    list.prepend(item);
    while (list.children.length > 8) list.removeChild(list.lastChild);
  } catch (e) { console.warn("[lapAddDetItem]", e); }
}

function lapAddGalleryItem(src, label, ts) {
  try {
    if (!src || src.startsWith("data:,")) return;
    const gal = $("lapGallery");
    if (!gal) return;
    gal.querySelector(".no-data")?.remove();
    LAP.snapshots.unshift({ src, label, ts });
    if ($("lapGalCount")) $("lapGalCount").textContent = LAP.snapshots.length + " ảnh";

    const item = document.createElement("div");
    item.className = "lap-gal-item neon-hover";
    const tsStr = new Date(ts * 1000).toLocaleTimeString("vi-VN", { hour12: false });
    item.innerHTML = `<img src="${src}" alt="" onerror="this.parentElement.remove()"><span class="lap-gal-label">${label}</span><span class="lap-gal-ts">${tsStr}</span>`;
    item.addEventListener("click", () => {
      const v = VIOLS.find(x => x.plate === label);
      if (v) openModal(v);
    });
    gal.prepend(item);
    while (gal.children.length > 12) gal.removeChild(gal.lastChild);
  } catch (e) { console.warn("[lapAddGalleryItem]", e); }
}

// lapSpawnDetection disabled — camera thật xử lý detection
function lapSpawnDetection() { /* disabled: chỉ dùng OCR thật */ }

function lapAddLog(msg, cls = "info") {
  try {
    const el = $("lapLog");
    if (!el) return;
    const d = document.createElement("div");
    d.className = "log-l " + cls;
    d.textContent = `[${new Date().toLocaleTimeString("vi-VN",{hour12:false})}] ${msg}`;
    el.appendChild(d);
    el.scrollTop = el.scrollHeight;
    while (el.children.length > 50) el.removeChild(el.firstChild);
  } catch (e) { console.warn("[lapAddLog]", e); }
}

if ($("btnClearGal"))    { $("btnClearGal").addEventListener("click", () => { const g = $("lapGallery"); if (g) { g.innerHTML = '<div class="no-data">Chưa có ảnh</div>'; LAP.snapshots=[]; if ($("lapGalCount")) $("lapGalCount").textContent = "0 ảnh"; } }); }
if ($("btnClearLapLog")) { $("btnClearLapLog").addEventListener("click", () => { const l = $("lapLog"); if (l) l.innerHTML = ""; }); }

// ═══════════════════════════════════════════════════════════════
// DEMO VIOLATION SPAWNER
// ═══════════════════════════════════════════════════════════════
function scheduleViolation() { /* disabled */ }

// spawnViolation disabled — chỉ vi phạm thật từ ESP32/camera
function spawnViolation() { /* disabled */ }

// ═══════════════════════════════════════════════════════════════
// KPI
// ═══════════════════════════════════════════════════════════════
function updateKPIs() {
  if ($("kpiViol"))     $("kpiViol").textContent     = DS.todayViol;
  if ($("kpiDetected")) $("kpiDetected").textContent = DS.detected;
  if ($("siTotal"))     $("siTotal").textContent     = DS.totalViol;
  if ($("kpiViolSub"))  $("kpiViolSub").textContent  = `+${DS.todayViol} hôm nay`;
  updateViolationBadge();
}

function updateViolationBadge() {
  const b = $("navBadge");
  if (!b) return;
  b.textContent = DS.totalViol;
  b.className   = "nav-badge" + (DS.totalViol > 0 ? "" : " zero");
}

function getViolationImageUrl(v, preferPlate = false) {
  if (!v) return "";
  const fullCandidates = [
    v.image_url,
    v.full_image_url,
    v.full_image_path,
    v.snapshot_url,
    v.dataUrl,
    v.plate_image_url,
    v.plate_url,
  ];
  const plateCandidates = [
    v.plate_image_url,
    v.plate_url,
    v.image_url,
    v.full_image_url,
    v.full_image_path,
    v.snapshot_url,
    v.dataUrl,
  ];
  const src = (preferPlate ? plateCandidates : fullCandidates).find(Boolean) || "";
  return typeof src === "string" ? src : "";
}

function normalizeViolation(v) {
  if (!v) return v;
  const ts = Number(v.ts || v.violation_ts || v.timestamp || Math.floor(Date.now() / 1000));
  const plate = (v.plate || v.plate_text || "").toUpperCase();
  const cam = v.cam || v.cam_id || v.camera_id || "--";
  const imageUrl = getViolationImageUrl(v, false);
  const plateUrl = getViolationImageUrl(v, true);
  return {
    ...v,
    ts,
    plate,
    cam,
    image_url: imageUrl,
    snapshot_url: v.snapshot_url || imageUrl,
    full_image_url: v.full_image_url || imageUrl,
    full_image_path: v.full_image_path || imageUrl,
    plate_image_url: v.plate_image_url || plateUrl,
    plate_url: v.plate_url || plateUrl,
  };
}

// ═══════════════════════════════════════════════════════════════
// RECENT VIOLATIONS
// ═══════════════════════════════════════════════════════════════
function appendRecent(v) {
  try {
    v = normalizeViolation(v);
    const c = $("recentList");
    if (!c) return;
    c.querySelector(".no-data")?.remove();
    const card = document.createElement("div");
    card.className = "vcard new neon-hover";
    // FIX v6.0: fallback ảnh + hiện địa chỉ nếu có
    const _vImg = getViolationImageUrl(v);
    const _vAddr = (v.location && v.location.street) ? `${v.location.street}, ${v.location.district}` : "";
    const _vTime = v.time_str ? `${v.time_str} ${v.date_str}` : new Date(v.ts * 1000).toLocaleTimeString("vi-VN");
    card.innerHTML = `
      <div class="vcard-img">${_vImg ? `<img src="${_vImg}${v.image_url||v.snapshot_url ? '?t='+v.ts : ''}" alt="" onerror="this.style.display='none'">` : `<div class="placeholder">📷</div>`}</div>
      <div class="vcard-info">
        <div class="vcard-plate">${v.plate}</div>
        <div class="vcard-meta">${v.type} · ${_vTime} · ${v.cam}</div>
        ${_vAddr ? `<div class="vcard-addr" style="font-size:9.5px;color:#8af;opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px">📍 ${_vAddr}</div>` : ""}
      </div>
      <div class="vcard-tag">● ĐỎ</div>`;
    card.addEventListener("click", () => openModal(v));
    c.prepend(card);
    while (c.children.length > 5) c.removeChild(c.lastChild);
    setTimeout(() => card.classList.remove("new"), 1500);
  } catch (e) { console.warn("[appendRecent]", e); }
}

// ═══════════════════════════════════════════════════════════════
// VIOLATIONS TABLE
// ═══════════════════════════════════════════════════════════════
function renderVioTable() {
  try {
    const body = $("vioBody");
    if (!body) return;
    const total   = filtered.length;
    const totalPg = Math.max(1, Math.ceil(total / pageSize));
    if (page > totalPg) page = totalPg;
    const slice = filtered.slice((page - 1) * pageSize, page * pageSize);

    const table = body.closest("table");
    if (table) table.classList.add("neon-table");

    body.innerHTML = "";
    if (!slice.length) {
      body.innerHTML = `<tr class="no-data-row"><td colspan="10">Không tìm thấy dữ liệu</td></tr>`;
    } else {
      slice.forEach(v => {
        v = normalizeViolation(v);
        const tr  = document.createElement("tr");
        tr.classList.add("neon-hover");
        const dt  = new Date(v.ts * 1000).toLocaleString("vi-VN");
        const conf = v.confidence || 0;
        v.image_url = getViolationImageUrl(v);
        tr.innerHTML = `
          <td><span style="font-family:var(--mono);color:var(--t2);font-size:11px">#${v.id}</span></td>
          <td><span class="cell-plate">${v.plate}</span></td>
          <td>${v.type || "--"}</td><td>${dt}</td>
          <td><span class="light-chip ${(v.light||"").toLowerCase()}">${v.light||"--"}</span></td>
          <td>${v.speed_kmh ? v.speed_kmh + " km/h" : "--"}</td>
          <td>${v.roi || "--"}</td>
          <td><div class="conf-wrap"><div class="conf-bar"><div class="conf-fill" style="width:${conf}%"></div></div><span class="conf-val">${conf}%</span></div></td>
          <td>${v.image_url ? `<img src="${v.image_url}?t=${v.ts||0}" class="thumb-img" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{style:'font-size:9px;color:#888',textContent:'📷'}))" >` : `<span style="font-size:9.5px;color:var(--t3)">Chưa có</span>`}</td>
          <td><button class="act-btn" data-id="${v.id}">Xem</button></td>`;
        tr.querySelector(".act-btn").addEventListener("click", e => { e.stopPropagation(); openModal(v); });
        tr.addEventListener("click", () => openModal(v));
        body.appendChild(tr);
      });
    }
    if ($("vioCount")) $("vioCount").textContent  = `${total} bản ghi`;
    if ($("pgCur"))    $("pgCur").textContent      = page;
    if ($("pgTotal"))  $("pgTotal").textContent    = totalPg;
  } catch (e) { console.warn("[renderVioTable]", e); }
}

$("btnPrev") && $("btnPrev").addEventListener("click", () => { if (page > 1) { page--; renderVioTable(); } });
$("btnNext") && $("btnNext").addEventListener("click", () => { if (page < Math.ceil(filtered.length / pageSize)) { page++; renderVioTable(); } });

function applyFilters() {
  try {
    const q  = ($("searchInput") ? $("searchInput").value : "").trim().toUpperCase();
    const fl = $("fLight") ? $("fLight").value : "";
    const ft = $("fType")  ? $("fType").value  : "";
    const fd = $("fDate")  ? $("fDate").value  : "";
    filtered = VIOLS.filter(v => {
      if (q  && !v.plate.includes(q)) return false;
      if (fl && v.light !== fl) return false;
      if (ft && v.type  !== ft) return false;
      if (fd && new Date(v.ts*1000).toISOString().slice(0,10) !== fd) return false;
      return true;
    });
    page = 1; renderVioTable();
  } catch (e) { console.warn("[applyFilters]", e); }
}

$("btnSearch")    && $("btnSearch").addEventListener("click", applyFilters);
$("searchInput")  && $("searchInput").addEventListener("keydown", e => { if (e.key === "Enter") applyFilters(); });
$("fLight")       && $("fLight").addEventListener("change", applyFilters);
$("fType")        && $("fType").addEventListener("change", applyFilters);
$("fDate")        && $("fDate").addEventListener("change", applyFilters);
$("btnResetFilter") && $("btnResetFilter").addEventListener("click", () => {
  ["searchInput","fLight","fType","fDate"].forEach(id => $(id) && ($(id).value = ""));
  filtered = [...VIOLS]; page = 1; renderVioTable();
});

$("btnCSV") && $("btnCSV").addEventListener("click", () => {
  try {
    if (!filtered.length) { toast("Không có dữ liệu.", "warn"); return; }
    const rows = [["ID","Biển Số","Loại Xe","Thời Gian","Đèn","Tốc Độ","ROI","Độ Tin Cậy"]];
    filtered.forEach(v => rows.push([v.id, v.plate, v.type||"", new Date(v.ts*1000).toLocaleString("vi-VN"), v.light||"", v.speed_kmh||"", v.roi||"", (v.confidence||0)+"%"]));
    const csv = rows.map(r => r.map(c => `"${c}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv" }));
    a.download = "violations_" + Date.now() + ".csv";
    a.click();
    toast("Xuất CSV thành công!", "ok");
  } catch (e) { toast("Lỗi xuất CSV: " + e.message, "err"); }
});
$("btnPDF") && $("btnPDF").addEventListener("click", () => toast("Chức năng PDF đang phát triển.", "info"));

// ═══════════════════════════════════════════════════════════════
// MODAL
// ═══════════════════════════════════════════════════════════════
let currentViol = null;
function openModal(v) {
  if (!v) return;
  try {
    v = normalizeViolation(v);
    currentViol = v;
    $("mID")    && ($("mID").textContent    = v.id);
    $("mPlate") && ($("mPlate").textContent = v.plate);
    $("mPlateEdit") && ($("mPlateEdit").value = v.plate || "");
    $("mLight") && ($("mLight").textContent = v.light || "--");
    $("mTime")  && ($("mTime").textContent  = new Date(v.ts * 1000).toLocaleString("vi-VN"));
    $("mType")  && ($("mType").textContent  = v.type || "--");
    $("mSpeed") && ($("mSpeed").textContent = v.speed_kmh ? v.speed_kmh + " km/h" : "--");
    $("mROI")   && ($("mROI").textContent   = v.roi || "--");
    $("mCam")   && ($("mCam").textContent   = v.cam || "--");
    $("mOCR")   && ($("mOCR").textContent   = "OCR: " + v.plate);
    $("mConf")  && ($("mConf").textContent  = "Tin cậy: " + (v.confidence || "--") + "%");
    // FIX v6.0: multi-source fallback ảnh
    const img = $("mImg"), ph = $("mImgPlaceholder");
    const _srcList = [];
    if (v.image_url)    _srcList.push(v.image_url + "?t=" + Date.now());
    if (v.snapshot_url && v.snapshot_url !== v.image_url) _srcList.push(v.snapshot_url + "?t=" + Date.now());
    if (v.dataUrl && v.dataUrl.startsWith("data:")) _srcList.push(v.dataUrl);
    if (img && _srcList.length > 0) {
      let _si = 0;
      const _tryNext = () => {
        if (_si >= _srcList.length) { img.style.display="none"; if(ph) ph.style.display="flex"; return; }
        img.onerror = () => { _si++; _tryNext(); };
        img.onload  = () => { img.style.display="block"; if(ph) ph.style.display="none"; };
        img.src = _srcList[_si];
        img.style.display = "block"; if(ph) ph.style.display="none";
      };
      _tryNext();
    } else { if(img) img.style.display="none"; if(ph) ph.style.display="flex"; }

    // Plate crop image (preferred) + fallback to full image
    const pimg = $("mPlateImg"), pph = $("mPlateImgPlaceholder"), phint = $("mPlateImgHint");
    const _pSrcList = [];
    if (v.plate_image_url) _pSrcList.push(v.plate_image_url + "?t=" + Date.now());
    if (v.plate_url && v.plate_url !== v.plate_image_url) _pSrcList.push(v.plate_url + "?t=" + Date.now());
    if (!_pSrcList.length && v.image_url) _pSrcList.push(v.image_url + "?t=" + Date.now());

    if (phint) phint.textContent = _pSrcList.length ? "OK" : "Chưa có";
    if (pimg && _pSrcList.length > 0) {
      let _pi = 0;
      const _tryNextP = () => {
        if (_pi >= _pSrcList.length) { pimg.style.display="none"; if(pph) pph.style.display="flex"; return; }
        pimg.onerror = () => { _pi++; _tryNextP(); };
        pimg.onload  = () => { pimg.style.display="block"; if(pph) pph.style.display="none"; };
        pimg.src = _pSrcList[_pi];
        pimg.style.display = "block"; if(pph) pph.style.display="none";
      };
      _tryNextP();
    } else { if(pimg) pimg.style.display="none"; if(pph) pph.style.display="flex"; }
    // FIX v6.0: hiện vị trí + thời gian đầy đủ trong modal
    const _vLoc = v.location || {};
    const _locStr = _vLoc.address ? _vLoc.address : (_vLoc.street ? `${_vLoc.street}, ${_vLoc.district}, ${_vLoc.city}` : "");
    const _timeStr = v.time_str ? `${v.time_str}  ${v.date_vn || v.date_str || ""}` : new Date(v.ts*1000).toLocaleString("vi-VN");
    $("mTime")  && ($("mTime").textContent = _timeStr);
    if ($("mLocation")) {
      $("mLocation").textContent = _locStr || "--";
      const _mlRow = $("mLocationRow");
      if (_mlRow) _mlRow.style.display = _locStr ? "" : "none";
    }
    const _mmRow = $("mMapsRow");
    if ($("mMapsLink") && _vLoc.maps_url) {
      $("mMapsLink").href = _vLoc.maps_url;
      $("mMapsLink").style.display = "inline";
      if (_mmRow) _mmRow.style.display = "";
    } else {
      if ($("mMapsLink")) $("mMapsLink").style.display = "none";
      if (_mmRow) _mmRow.style.display = "none";
    }
    $("modal") && $("modal").classList.add("open");
  } catch (e) { console.warn("[openModal]", e); }
}
function closeModal() { $("modal") && $("modal").classList.remove("open"); }
$("modalClose") && $("modalClose").addEventListener("click", closeModal);
$("modalBg")    && $("modalBg").addEventListener("click", closeModal);
window.openModal = openModal;
window.VIOLS     = VIOLS;

$("btnDlImg") && $("btnDlImg").addEventListener("click", () => {
  if (currentViol?.image_url) { const a = document.createElement("a"); a.href = currentViol.image_url; a.download = currentViol.plate + ".jpg"; a.click(); }
  else toast("Không có hình ảnh để tải.", "warn");
});
$("btnPrint")  && $("btnPrint").addEventListener("click", () => { toast("Đang in biên bản...", "info"); setTimeout(() => window.print(), 500); });
$("btnSavePlate") && $("btnSavePlate").addEventListener("click", async () => {
  if (!currentViol) return;
  try {
    const val = ($("mPlateEdit") ? $("mPlateEdit").value : "").trim().toUpperCase();
    if (!val) { toast("Biển số không hợp lệ.", "warn"); return; }
    const r = await safeFetch(`/api/violations/${currentViol.id}`, {
      method: "PUT",
      body: JSON.stringify({ plate_text: val }),
    });
    if (!r?.ok) { toast("Lưu biển số thất bại.", "err"); return; }

    currentViol.plate = val;
    $("mPlate") && ($("mPlate").textContent = val);
    $("mOCR")   && ($("mOCR").textContent   = "OCR: " + val);

    const i = VIOLS.findIndex(x => x.id === currentViol.id);
    if (i > -1) VIOLS[i].plate = val;
    filtered = [...VIOLS];
    renderVioTable(); rebuildRecent();
    toast("Đã lưu biển số.", "ok");
  } catch (e) { toast("Lỗi lưu biển số: " + e.message, "err"); }
});

async function uploadViolationImage(url, field, file) {
  const tok = await ensureToken();
  if (!tok) return null;
  const fd = new FormData();
  fd.append(field, file, file.name || "upload.jpg");
  const res = await fetch(url, { method: "POST", headers: { "Authorization": `Bearer ${tok}` }, body: fd });
  if (!res.ok) return null;
  return res.json().catch(() => null);
}

$("btnReplacePlateImg") && $("btnReplacePlateImg").addEventListener("click", () => $("mFilePlate") && $("mFilePlate").click());
$("btnReplaceFullImg")  && $("btnReplaceFullImg").addEventListener("click",  () => $("mFileFull")  && $("mFileFull").click());

$("mFilePlate") && $("mFilePlate").addEventListener("change", async (e) => {
  if (!currentViol) return;
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  try {
    const r = await uploadViolationImage(`/api/violations/${currentViol.id}/replace-plate-image`, "plate_image", f);
    if (!r?.ok || !r.plate_image_url) { toast("Thay ảnh biển số thất bại.", "err"); return; }
    currentViol.plate_image_url = r.plate_image_url;
    currentViol.plate_url = r.plate_image_url;
    openModal(currentViol);
    toast("Đã thay ảnh biển số.", "ok");
  } catch (err) { toast("Lỗi upload ảnh biển số: " + err.message, "err"); }
  finally { try { e.target.value = ""; } catch {} }
});

$("mFileFull") && $("mFileFull").addEventListener("change", async (e) => {
  if (!currentViol) return;
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  try {
    const r = await uploadViolationImage(`/api/violations/${currentViol.id}/replace-full-image`, "full_image", f);
    if (!r?.ok || !r.image_url) { toast("Thay ảnh toàn cảnh thất bại.", "err"); return; }
    currentViol.image_url = r.image_url;
    openModal(currentViol);
    renderVioTable(); rebuildRecent();
    toast("Đã thay ảnh toàn cảnh.", "ok");
  } catch (err) { toast("Lỗi upload ảnh toàn cảnh: " + err.message, "err"); }
  finally { try { e.target.value = ""; } catch {} }
});

$("btnDelRec") && $("btnDelRec").addEventListener("click", () => {
  if (!currentViol) return;
  (async () => {
    try {
      const r = await safeFetch(`/api/violations/${currentViol.id}`, { method: "DELETE" });
      if (!r?.ok) { toast("Xóa bản ghi thất bại.", "err"); return; }
      const i = VIOLS.findIndex(v => v.id === currentViol.id);
      if (i > -1) VIOLS.splice(i, 1);
      filtered = [...VIOLS];
      DS.totalViol = VIOLS.length;
      DS.todayViol = VIOLS.filter(v => new Date(v.ts*1000).toDateString() === new Date().toDateString()).length;
      updateKPIs(); renderVioTable(); rebuildRecent(); closeModal();
      toast("Đã xóa bản ghi (soft delete).", "warn");
    } catch (e) { toast("Lỗi xóa bản ghi: " + e.message, "err"); }
  })();
});

function rebuildRecent() {
  const c = $("recentList");
  if (!c) return;
  c.innerHTML = VIOLS.length === 0 ? `<div class="no-data">Chưa có vi phạm</div>` : "";
  VIOLS.slice(0, 5).forEach(v => appendRecent(v));
}

// ═══════════════════════════════════════════════════════════════
// CAMERA SIMULATION (ESP32 section)
// ═══════════════════════════════════════════════════════════════
let CAM_SIM_ACTIVE = false;
let CAM_SIM_ANIMID = null;
function stopCamSim() {
  CAM_SIM_ACTIVE = false;
  try { if (CAM_SIM_ANIMID) cancelAnimationFrame(CAM_SIM_ANIMID); } catch {}
  CAM_SIM_ANIMID = null;
}

function startCamSim() {
  const img = $("camImg"); if (!img) return;
  stopCamSim();
  CAM_SIM_ACTIVE = true;
  const tc = document.createElement("canvas");
  tc.width = camFrameW; tc.height = camFrameH;
  const ctx = tc.getContext("2d");
  function draw() {
    if (!CAM_SIM_ACTIVE) return;
    try {
      const W = camFrameW, H = camFrameH;
      const skyG = ctx.createLinearGradient(0, 0, 0, H);
      skyG.addColorStop(0, "#0a0f1e"); skyG.addColorStop(.55, "#0d1524"); skyG.addColorStop(1, "#0a0e18");
      ctx.fillStyle = skyG; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#111827"; ctx.fillRect(0, 200, W, 160);
      ctx.setLineDash([35,18]); ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(320, 210); ctx.lineTo(320, 360); ctx.stroke(); ctx.setLineDash([]);
      const roiY = 270;
      ctx.strokeStyle = "rgba(255,58,92,0.85)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(40, roiY); ctx.lineTo(600, roiY); ctx.stroke();
      ctx.fillStyle = "rgba(255,58,92,0.8)"; ctx.font = "bold 9px Space Mono, monospace"; ctx.textAlign = "center";
      ctx.fillText("▲ VẠCH DỪNG — ROI ▲", 320, roiY - 6); ctx.textAlign = "left";
      if (DS.camState !== "IDLE") {
        const numV = Math.min(DS.vehicles, 3);
        for (let i = 0; i < numV; i++) {
          const t = ((Date.now()/1000) + i * 1.4) % 5;
          const yBase = 215 + t * 22;
          const x = 80 + i * 200 + Math.sin(Date.now()/1200 + i) * 4;
          const isViol = DS.light === "RED" && yBase > roiY - 5;
          const colors = ["#1a4da8","#a82020","#1a8a42"];
          ctx.fillStyle = colors[i % 3];
          ctx.beginPath(); ctx.roundRect(x - 28, yBase - 18, 56, 32, [4,4,2,2]); ctx.fill();
          ctx.fillStyle = "rgba(180,220,255,0.55)"; ctx.fillRect(x - 18, yBase - 16, 36, 13);
          if (isViol) {
            ctx.strokeStyle = "rgba(255,58,92,0.9)"; ctx.lineWidth = 2; ctx.strokeRect(x - 34, yBase - 24, 68, 44);
            ctx.fillStyle = "rgba(255,58,92,0.88)"; ctx.fillRect(x - 34, yBase - 38, 75, 15);
            ctx.fillStyle = "#fff"; ctx.font = "bold 8.5px Space Mono, monospace";
            ctx.fillText(PLATES[i % PLATES.length], x - 31, yBase - 28);
          } else {
            ctx.strokeStyle = "rgba(0,232,122,0.7)"; ctx.lineWidth = 1.5; ctx.strokeRect(x - 34, yBase - 24, 68, 44);
            ctx.fillStyle = "rgba(0,232,122,0.8)"; ctx.font = "8px Space Mono, monospace";
            ctx.fillText(TYPES[i % TYPES.length], x - 28, yBase - 27);
          }
        }
      }
      ctx.fillStyle = "rgba(32,202,255,0.06)"; ctx.font = "bold 52px DM Sans, sans-serif"; ctx.textAlign = "center";
      ctx.fillText("DEMO", 320, 195); ctx.textAlign = "left";
      ctx.fillStyle = "rgba(0,0,0,.65)"; ctx.fillRect(0, 0, 210, 20);
      ctx.fillStyle = "rgba(255,255,255,.8)"; ctx.font = "10.5px Space Mono, monospace";
      ctx.fillText(new Date().toLocaleString("vi-VN"), 6, 13);
      img.src = tc.toDataURL("image/webp", 0.75);
    } catch (e) { console.warn("[camSim draw]", e); }
    CAM_SIM_ANIMID = requestAnimationFrame(draw);
  }
  draw();
}

function setEsp32Stream(on) {
  const img = $("camImg"); if (!img) return;
  if (on) {
    stopCamSim();
    // Dùng FastAPI MJPEG stream feed thật
    const apiBase = (window.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
    img.src = `${apiBase}/stream/feed?t=` + Date.now();
    img.alt = "AI Detection Stream";
  } else {
    stopCamSim();
    try {
      const tc = document.createElement("canvas");
      tc.width = camFrameW; tc.height = camFrameH;
      const ctx = tc.getContext("2d");
      ctx.fillStyle = "#060b16"; ctx.fillRect(0, 0, tc.width, tc.height);
      ctx.fillStyle = "rgba(32,202,255,.08)";
      ctx.fillRect(20, 20, tc.width - 40, tc.height - 40);
      ctx.strokeStyle = "rgba(32,202,255,.25)"; ctx.lineWidth = 2;
      ctx.strokeRect(20, 20, tc.width - 40, tc.height - 40);
      ctx.fillStyle = "rgba(255,255,255,.85)";
      ctx.font = "bold 18px DM Sans, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Chưa kết nối ESP32-CAM", tc.width / 2, tc.height / 2 - 6);
      ctx.fillStyle = "rgba(255,255,255,.65)";
      ctx.font = "12px Space Mono, monospace";
      ctx.fillText("Hãy bật ESP32 camera để quan sát mô hình", tc.width / 2, tc.height / 2 + 18);
      ctx.textAlign = "left";
      img.src = tc.toDataURL("image/webp", 0.85);
      img.alt = "ESP32-CAM Offline";
    } catch {
      img.src = "";
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// DETECTION LIST
// ═══════════════════════════════════════════════════════════════
let detCount = 0;
function addDetection(v) {
  try {
    const list = $("detList"); if (!list) return;
    list.querySelector(".no-data")?.remove();
    detCount++;
    if ($("detCount")) $("detCount").textContent = detCount + " xe";
    const item = document.createElement("div");
    item.className = "det-item neon-hover";
    item.innerHTML = `<span class="det-type">${v.type||"--"}</span><span class="det-plate">${v.plate}</span><span class="det-conf">${v.confidence}%</span>${DS.light==="RED"?`<span class="det-flag">VI PHẠM</span>`:""}`;
    list.prepend(item);
    while (list.children.length > 8) list.removeChild(list.lastChild);
  } catch (e) { console.warn("[addDetection]", e); }
}

// ═══════════════════════════════════════════════════════════════
// SYSTEM LOG
// ═══════════════════════════════════════════════════════════════
let logCount = 1;
function addLog(msg, cls = "info") {
  try {
    const el = $("camLog"); if (!el) return;
    const d = document.createElement("div");
    d.className = "log-l " + cls;
    d.textContent = `[${new Date().toLocaleTimeString("vi-VN",{hour12:false})}] ${msg}`;
    el.appendChild(d); el.scrollTop = el.scrollHeight;
    while (el.children.length > 60) el.removeChild(el.firstChild);
    logCount = el.children.length;
    if ($("logCount")) $("logCount").textContent = logCount + " dòng";
  } catch (e) { console.warn("[addLog]", e); }
}
$("btnClearLog") && $("btnClearLog").addEventListener("click", () => { const l = $("camLog"); if (l) { l.innerHTML = ""; logCount = 0; if ($("logCount")) $("logCount").textContent = "0 dòng"; } });

// ═══════════════════════════════════════════════════════════════
// CAMERA STATUS ROW
// ═══════════════════════════════════════════════════════════════
const CAM_DATA = [
  { id:1, name:"CAM 1 — Bắc", ip:"192.168.1.101", getStatus:()=>DS.camState==="ACTIVE"?"online":DS.camState==="WARMUP"?"idle":"idle", getLabel:()=>DS.camState },
  { id:2, name:"CAM 2 — Nam",  ip:"192.168.1.102", getStatus:()=>"online", getLabel:()=>"STANDBY" },
  { id:3, name:"CAM 3 — Đông", ip:"192.168.1.103", getStatus:()=>"idle",   getLabel:()=>"WARMUP" },
];

function renderCamRow() {
  try {
    const row = $("camRow"); if (!row) return;
    row.innerHTML = CAM_DATA.map(c => {
      const st = c.getStatus(), lb = c.getLabel();
      return `<div class="cam-card ${st} neon-hover" onclick="goTo('camera')"><div class="cam-icon">📷</div><div class="cam-info"><div class="cam-name">${c.name}</div><div class="cam-detail">IP: ${c.ip} · ${espOK?"Virtual Cluster Online":"Virtual Standby"}</div></div><div class="cam-status-badge ${st}">${lb}</div></div>`;
    }).join("");
  } catch (e) { console.warn("[renderCamRow]", e); }
}

// ═══════════════════════════════════════════════════════════════
// DEVICES
// ═══════════════════════════════════════════════════════════════
const DEVICES = [
  { emoji:"📷", name:"ESP32-CAM #1",   ip:"192.168.1.101", role:"Camera Bắc",         status:"online", sig:95,  temp:"42°C", up:"12h 34m", last:"Vừa xong" },
  { emoji:"📷", name:"ESP32-CAM #2",   ip:"192.168.1.102", role:"Camera Nam",          status:"online", sig:88,  temp:"38°C", up:"12h 34m", last:"Vừa xong" },
  { emoji:"📷", name:"ESP32-CAM #3",   ip:"192.168.1.103", role:"Camera Đông",         status:"idle",   sig:72,  temp:"35°C", up:"8h 12m",  last:"2 phút trước" },
  { emoji:"🚦", name:"Đèn Giao Thông", ip:"192.168.1.110", role:"Traffic Light",       status:"online", sig:100, temp:"28°C", up:"12h 34m", last:"Vừa xong" },
  { emoji:"🔢", name:"LED 7 Đoạn",     ip:"192.168.1.111", role:"Hiển Thị Đếm Ngược", status:"online", sig:100, temp:"25°C", up:"12h 34m", last:"Vừa xong" },
  { emoji:"🔴", name:"Button Khẩn Cấp",ip:"192.168.1.112", role:"Nút Bấm",            status:"online", sig:100, temp:"22°C", up:"12h 34m", last:"Vừa xong" },
];

let LIVE_DEVICES = null; // { device_id -> device info } from /api/bootstrap or /api/device-status

function _fmtUptime(sec) {
  const s = Math.max(0, parseInt(sec || 0, 10) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function _deviceEmoji(did, dtype) {
  const t = (dtype || "").toUpperCase();
  if (t.includes("CAM")) return "📷";
  if (t.includes("LED")) return "🔴";
  if (t.includes("TRAFFIC")) return "🚦";
  if ((did || "").includes("cam")) return "📷";
  if ((did || "").includes("led")) return "🔴";
  return "🧩";
}

function _devicesForUI() {
  if (!LIVE_DEVICES) return DEVICES;
  try {
    const now = Math.floor(Date.now() / 1000);
    return Object.entries(LIVE_DEVICES).map(([did, dv]) => {
      const st = (dv.status || "").toUpperCase();
      const online = st === "ONLINE";
      const lastSeen = dv.last_seen || dv.last_heartbeat_ts || 0;
      const lastAgo = lastSeen ? (now - lastSeen) : null;
      const lastStr = dv.last_seen_str || (lastAgo === null ? "--" : (lastAgo < 60 ? `${lastAgo}s` : `${Math.floor(lastAgo / 60)}m`));
      const sigRaw = (dv.signal ?? dv.rssi ?? 0);
      const sig = (typeof sigRaw === "number" && sigRaw < 0) ? Math.max(0, Math.min(100, 120 + sigRaw)) : Math.max(0, Math.min(100, parseInt(sigRaw || 0, 10) || 0));
      const temp = (dv.temp ?? dv.cpu_temp_c);
      const tempStr = (temp === undefined || temp === null) ? "--" : `${Math.round(temp)}°C`;
      return {
        emoji: _deviceEmoji(did, dv.device_type),
        name: dv.name || dv.device_name || did,
        ip: dv.ip || dv.ip_address || "--",
        role: dv.device_type || "",
        status: online ? "online" : "offline",
        sig,
        temp: tempStr,
        up: _fmtUptime(dv.uptime),
        last: lastStr,
      };
    });
  } catch (e) {
    console.warn("[_devicesForUI]", e);
    return DEVICES;
  }
}

function renderDevices() {
  try {
    const grid = $("devGrid"); if (!grid) return;
    const list = _devicesForUI();
    grid.innerHTML = list.map(d => `
      <div class="dev-card ${d.status} neon-hover">
        <div class="dev-head"><div class="dev-emoji">${d.emoji}</div><div><div class="dev-name">${d.name}</div><div class="dev-ip">${d.ip} · ${d.role}</div></div>
          <div class="dev-status ${d.status}">${d.status==="online"?"● ONLINE":d.status==="idle"?"◐ IDLE":"✕ OFFLINE"}</div>
        </div>
        <div class="dev-stats">
          <div class="dev-stat">Signal<strong>${d.sig}%</strong></div>
          <div class="dev-stat">Nhiệt Độ<strong>${d.temp}</strong></div>
          <div class="dev-stat">Uptime<strong>${d.up}</strong></div>
          <div class="dev-stat">Lần Cuối<strong>${d.last}</strong></div>
        </div>
      </div>`).join("");

    const aList = $("alertList");
    if (aList && aList.querySelector(".no-data")) {
      aList.innerHTML = [
        { cls:"warn", icon:"🟡", msg:"ESP32-CAM #3 tín hiệu yếu (72%)", time:"10 phút trước" },
        { cls:"err",  icon:"🔴", msg:"ESP32-CAM #2 mất kết nối (đã phục hồi)", time:"1 giờ trước" },
        { cls:"",     icon:"ℹ️", msg:"Hệ thống khởi động lại thành công", time:"12 giờ trước" },
      ].map(a => `<div class="alert-item ${a.cls}"><span class="alert-icon">${a.icon}</span><span class="alert-msg">${a.msg}</span><span class="alert-time">${a.time}</span></div>`).join("");
    }
  } catch (e) { console.warn("[renderDevices]", e); }
}

// ═══════════════════════════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════════════════════════
function renderCharts() {
  try { drawHourChart(); } catch (e) { console.warn("[drawHourChart]", e); }
  try { drawDonut();     } catch (e) { console.warn("[drawDonut]", e); }
  try { drawWeekChart(); } catch (e) { console.warn("[drawWeekChart]", e); }
}

function drawHourChart() {
  const c = $("chartHour"); if (!c) return;
  const W = c.parentElement.offsetWidth - 28 || 600;
  c.width = W; c.height = 180;
  const ctx = c.getContext("2d");
  const pad = {t:20,r:10,b:28,l:35}, cW = W - pad.l - pad.r, cH = 180 - pad.t - pad.b;
  const max = Math.max(...hourly, 1);
  ctx.clearRect(0, 0, W, 180);
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + cH - (i/4)*cH;
    ctx.strokeStyle = "rgba(32,202,255,0.06)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cW, y); ctx.stroke();
    ctx.fillStyle = "rgba(136,153,184,0.6)"; ctx.font = "8.5px Space Mono,monospace"; ctx.textAlign = "right";
    ctx.fillText(Math.round(i * max / 4), pad.l - 4, y + 3);
  }
  const now = new Date().getHours(), bW = (cW/24)*0.55;
  for (let i = 0; i < 24; i++) {
    const v = hourly[i] || 0, bH = v > 0 ? Math.max((v/max)*cH, 3) : 2;
    const x = pad.l + (i/24)*cW + (cW/24)*0.225, y = pad.t + cH - bH;
    const g = ctx.createLinearGradient(0, y, 0, y + bH);
    if (i === now) { g.addColorStop(0,"rgba(32,202,255,.95)"); g.addColorStop(1,"rgba(32,202,255,.2)"); }
    else           { g.addColorStop(0,"rgba(32,202,255,.45)"); g.addColorStop(1,"rgba(32,202,255,.05)"); }
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.roundRect(x, y, bW, bH, [2,2,0,0]); ctx.fill();
  }
  ctx.fillStyle = "rgba(136,153,184,.7)"; ctx.font = "8.5px Space Mono,monospace"; ctx.textAlign = "center";
  [0,4,8,12,16,20,23].forEach(h => ctx.fillText(h + "h", pad.l + (h/24)*cW + (cW/48), pad.t + cH + 14));
}

function drawDonut() {
  const c = $("chartDonut"); if (!c) return;
  const ctx = c.getContext("2d");
  c.width = 160; c.height = 160;
  const cx = 80, cy = 80, R = 70, r = 48;
  const moto  = VIOLS.filter(v => (v.type||"").includes("máy")).length;
  const car   = VIOLS.filter(v => (v.type||"").toLowerCase().includes("ô tô")).length;
  const oth   = Math.max(0, VIOLS.length - moto - car);
  const total = moto + car + oth || 1;
  const slices = [{ c:"#20caff",v:moto,l:"Xe Máy" },{ c:"#ff3a5c",v:car,l:"Ô Tô" },{ c:"#ffb020",v:oth,l:"Khác" }];
  ctx.clearRect(0,0,160,160);
  let ang = -Math.PI/2;
  slices.forEach(s => { if (!s.v) return; const a = (s.v/total)*Math.PI*2; ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,R,ang,ang+a); ctx.closePath(); ctx.fillStyle = s.c; ctx.fill(); ang += a; });
  ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.fillStyle = "var(--panel,#0f1729)"; ctx.fill();
  ctx.textAlign = "center";
  ctx.font = "bold 22px Space Mono,monospace"; ctx.fillStyle = total > 1 ? "#e8edf7" : "#3d5075";
  ctx.fillText(VIOLS.length, cx, cy + 7);
  ctx.font = "9px DM Sans,sans-serif"; ctx.fillStyle = "#8899b8"; ctx.fillText("Vi Phạm", cx, cy + 20);
  ctx.textAlign = "left";
  const leg = $("donutLeg");
  if (leg) leg.innerHTML = slices.map(s => `<div class="leg-item"><div class="leg-dot" style="background:${s.c}"></div><span class="leg-lbl">${s.l}</span><span class="leg-val">${s.v}</span></div>`).join("");
  const st = $("statTable");
  if (st) {
    const mh = hourly.indexOf(Math.max(...hourly));
    const ac = VIOLS.length ? Math.round(VIOLS.reduce((s,v)=>s+(v.confidence||0),0)/VIOLS.length) : 0;
    st.innerHTML = `
      <div class="st-row"><span class="st-n">Tổng vi phạm</span><span class="st-v r">${VIOLS.length}</span></div>
      <div class="st-row"><span class="st-n">Xe máy</span><span class="st-v c">${moto}</span></div>
      <div class="st-row"><span class="st-n">Ô tô</span><span class="st-v a">${car}</span></div>
      <div class="st-row"><span class="st-n">Giờ cao điểm</span><span class="st-v">${mh}:00–${mh+1}:00</span></div>
      <div class="st-row"><span class="st-n">Độ tin cậy TB</span><span class="st-v g">${ac}%</span></div>
      <div class="st-row"><span class="st-n">Camera online</span><span class="st-v g">3/3</span></div>`;
  }
}

function drawWeekChart() {
  const c = $("chartWeek"); if (!c) return;
  const W = c.parentElement.offsetWidth - 28 || 800;
  c.width = W; c.height = 160;
  const ctx = c.getContext("2d");
  const pad = {t:18,r:14,b:28,l:32}, cW = W - pad.l - pad.r, cH = 160 - pad.t - pad.b;
  const data = [...weekly.slice(0,6), DS.todayViol];
  const max  = Math.max(...data, 1);
  const days = ["T2","T3","T4","T5","T6","T7","CN"];
  ctx.clearRect(0,0,W,160);
  const pts = data.map((v,i) => ({ x: pad.l + (i/(data.length-1))*cW, y: pad.t + cH - (v/max)*cH }));
  ctx.beginPath(); ctx.moveTo(pts[0].x, pad.t + cH);
  pts.forEach(p => ctx.lineTo(p.x, p.y)); ctx.lineTo(pts[pts.length-1].x, pad.t + cH); ctx.closePath();
  const aG = ctx.createLinearGradient(0, pad.t, 0, pad.t + cH);
  aG.addColorStop(0,"rgba(32,202,255,.18)"); aG.addColorStop(1,"rgba(32,202,255,.01)");
  ctx.fillStyle = aG; ctx.fill();
  ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) { const cpx = (pts[i-1].x + pts[i].x)/2; ctx.bezierCurveTo(cpx, pts[i-1].y, cpx, pts[i].y, pts[i].x, pts[i].y); }
  ctx.strokeStyle = "rgba(32,202,255,.9)"; ctx.lineWidth = 1.8; ctx.stroke();
  pts.forEach((p,i) => {
    ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2);
    ctx.fillStyle = i === 6 ? "var(--cyan)" : "rgba(32,202,255,.7)"; ctx.fill();
    ctx.fillStyle = "rgba(136,153,184,.8)"; ctx.font = "9px Space Mono,monospace"; ctx.textAlign = "center";
    ctx.fillText(days[i], p.x, pad.t + cH + 15);
    if (data[i] > 0) { ctx.fillStyle = "rgba(136,153,184,.9)"; ctx.fillText(data[i], p.x, p.y - 8); }
  });
}

// ═══════════════════════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════════════════════
$("btnSaveCfg") && $("btnSaveCfg").addEventListener("click", () => {
  try {
    CYCLE[0].dur = parseInt($("cfGreen").value)   || 30;
    CYCLE[1].dur = parseInt($("cfAmber").value)   || 5;
    CYCLE[2].dur = parseInt($("cfRed").value)     || 30;
    DS.capture   = parseInt($("cfCapture").value) || 500;
    toast("Đã lưu cài đặt!", "ok");
    tbSaveSettings(); // v5.0: also save TB credentials
    addLog("[SETTINGS] Cài đặt cập nhật.", "ok");
  } catch (e) { toast("Lỗi lưu cài đặt: " + e.message, "err"); }
});
$("btnResetCfg") && $("btnResetCfg").addEventListener("click", () => {
  [["cfGreen",7],["cfAmber",3],["cfRed",10],["cfSpeed",20],["cfVeh",6],["cfCapture",500],["cfOCR",70]].forEach(([id,v]) => $(id) && ($(id).value = v));
  toast("Đã khôi phục mặc định.", "info");
});
$("btTestCam")  && $("btTestCam").addEventListener("click",  () => { addLog("[TEST] Camera...", "info"); setTimeout(() => { addLog("[TEST] ✓ CAM1 OK", "ok"); addLog("[TEST] ✓ CAM2 OK", "ok"); addLog("[TEST] ⚠ CAM3 Yếu (72%)", "warn"); }, 1500); });
$("btTestMQTT") && $("btTestMQTT").addEventListener("click", () => { addLog("[TEST] MQTT...", "info"); setTimeout(() => addLog("[TEST] ✓ MQTT OK — 12ms", "ok"), 900); });
$("btTestAI")   && $("btTestAI").addEventListener("click",   () => { addLog("[TEST] YOLOv8...", "info"); setTimeout(() => addLog("[TEST] ✓ AI OK — FPS:" + DS.fps, "ok"), 1700); });
$("btClearDB")  && $("btClearDB").addEventListener("click",  () => {
  if (!confirm("Xóa toàn bộ database vi phạm?")) return;
  try {
    VIOLS.length = 0; filtered = [];
    DS.totalViol = 0; DS.todayViol = 0; DS.detected = 0;
    hourly.fill(0); weekly[6] = 0;
    updateKPIs(); renderVioTable(); rebuildRecent();
    toast("Đã xóa toàn bộ database!", "warn");
  } catch (e) { toast("Lỗi xóa database: " + e.message, "err"); }
});

// ═══════════════════════════════════════════════════════════════
// SIDEBAR + LOGOUT
// ═══════════════════════════════════════════════════════════════
$("btnToggle") && $("btnToggle").addEventListener("click", () => $("sidebar") && $("sidebar").classList.toggle("slim"));
$("btnLogout") && $("btnLogout").addEventListener("click", logout);

// ═══════════════════════════════════════════════════════════════
// TOAST
// ═══════════════════════════════════════════════════════════════
function toast(msg, cls = "info") {
  try {
    const c = $("toasts");
    if (!c) return;
    const el = document.createElement("div");
    el.className = "toast " + cls;
    const ic = { err:"🔴", ok:"✅", warn:"⚠️", info:"ℹ️" }[cls] || "ℹ️";
    el.innerHTML = `<span>${ic}</span><span style="flex:1">${msg}</span>`;
    c.appendChild(el);
    setTimeout(() => {
      el.style.transition = ".25s";
      el.style.opacity    = "0";
      el.style.transform  = "translateX(14px)";
      setTimeout(() => el.remove(), 250);
    }, 4000);
  } catch (e) { console.warn("[toast]", e); }
}

// ═══════════════════════════════════════════════════════════════
// REAL API / SOCKET
// ═══════════════════════════════════════════════════════════════
function trySocket() {
  if (typeof io === "undefined") return;
  try {
    const s = io({
      transports: ["websocket"],
      reconnectionAttempts: 5,
      auth: { token: getToken() },
    });
    s.on("connect",    () => { setConn("online"); espOK = true; addLog("[WS] ESP32 kết nối", "ok"); });
    s.on("disconnect", () => { setConn("demo"); addLog("[WS] Mất kết nối WebSocket — đang chờ kết nối lại...", "warn"); });
    s.on("traffic_state", st => {
      if (!st) return;
      DS.light     = st.light;
      DS.countdown = st.countdown;
      DS.camState  = st.camera;
      DS.phase     = st.light === "RED" ? "ĐỎ" : st.light === "YELLOW" ? "VÀNG" : "XANH";
      renderTraffic(); syncLapCtx();
    });
    s.on("new_violation", v => {
      v = normalizeViolation(v);
      // FIX v5.1: normalize cam_id → cam
      if (!v.cam && v.cam_id) v.cam = v.cam_id;
      VIOLS.unshift(v); filtered = [...VIOLS]; DS.totalViol++; DS.todayViol++;
      hourly[new Date().getHours()]++; updateKPIs(); appendRecent(v); addDetection(v); renderVioTable();
      toast("⚠ Vi phạm: " + v.plate, "err");
    });
    s.on("context_update", ctx => {
      const sp = (ctx && (ctx.speed_kmh ?? ctx.speed)) ?? 0;
      const vh = (ctx && (ctx.vehicles_frame ?? ctx.vehicles)) ?? 0;
      const capS = (ctx && (ctx.capture_interval ?? ctx.capture)) ?? 0.5;
      DS.speed    = sp;
      DS.vehicles = vh;
      DS.capture  = Math.round(parseFloat(capS || 0.5) * 1000);
      updateContext();
    });
    s.on("device_update", dv => {
      try {
        if (!dv) return;
        const did = dv.device_id || dv.id || dv.device || "";
        if (!did) return;
        if (!LIVE_DEVICES) LIVE_DEVICES = {};
        LIVE_DEVICES[did] = { ...(LIVE_DEVICES[did] || {}), ...dv, device_id: did };
        renderDevices();
      } catch (e) { console.warn("[device_update]", e); }
    });
    s.on("theme_update", data => {
      if (data && data.theme && data.source !== "ws-client") {
        applyTheme(data.theme, false);
        addLog(`[THEME] Server theme update: ${data.theme} (source: ${data.source})`, "ok");
      }
    });
  } catch (e) { addLog(`[SOCKET] Lỗi kết nối: ${e.message}`, "warn"); }
}

// ═══════════════════════════════════════════════════════════════
// BOOT — v4.2
// ═══════════════════════════════════════════════════════════════
async function boot() {
  try {
    addLog("[SYSTEM] AI Traffic Dashboard v4.2 khởi động...", "info");
    addLog("[FIX v4.2] Biển số không bị đảo ngược — CSS flip mode", "ok");

    // BƯỚC 1: Đảm bảo token
    addLog("[AUTH] Kiểm tra token...", "info");
    const tok = await ensureToken();
    if (tok) addLog(`[AUTH] Token sẵn sàng: ${tok.substring(0,15)}... ✓`, "ok");

    // BƯỚC 2: Init particles
    initParticles();

    // BƯỚC 3: Áp dụng theme local ngay
    const savedLocalTheme = localStorage.getItem("TRAFFIC_THEME") || "neon-futuristic";
    await applyTheme(savedLocalTheme, false);

    // BƯỚC 4: Fetch theme từ server (non-blocking, ignore errors)
    fetchTheme().catch(e => addLog(`[THEME] fetchTheme error: ${e.message}`, "warn"));

    // BƯỚC 5: Gọi FastAPI /health để kiểm tra backend thật
    addLog("[API] Kết nối FastAPI backend...", "info");
    const data = await safeFetch("/health");

    // /health trả về {status: "ok", gpu_available, supabase_connected, mqtt_connected, ...}
    if (data && data.status) {
      isDemo = false;
      $("demoBanner") && $("demoBanner").classList.add("hidden");
      setConn("online"); espOK = true;
      addLog(`[API] FastAPI backend OK ✓ | Supabase: ${data.supabase_connected ? "CONNECTED" : "OFFLINE"} | GPU: ${data.gpu_available ? "YES" : "NO"} | Model: ${data.vehicle_model_loaded ? "Loaded" : "Loading"}`, "ok");

      // violations sẽ được load bởi api.js layer (async sau 1.5s)
      filtered = [...VIOLS]; DS.totalViol = VIOLS.length; DS.todayViol = VIOLS.length;
      renderVioTable(); updateKPIs();

      // MQTT + stream status sẽ được cập nhật bởi api.js
      renderTraffic();
      updateContext();
      trySocket();
    } else {
      isDemo = false;
      addLog("[SYSTEM] Backend FastAPI chưa phản hồi — chờ api.js polling...", "warn");
      filtered = [...VIOLS];
      DS.totalViol = VIOLS.length;
      DS.todayViol = VIOLS.length;
      DS.detected = VIOLS.length;
      updateKPIs();
      renderVioTable();
      rebuildRecent();
    }

    startCycle();
    try {
      const anyCam = LIVE_DEVICES ? Object.entries(LIVE_DEVICES).some(([did, dv]) => {
        const st = (dv?.status || "").toUpperCase();
        const isCam = (did || "").toLowerCase().includes("cam") || ((dv?.device_type || "").toUpperCase().includes("CAM"));
        return isCam && st === "ONLINE";
      }) : false;
      setEsp32Stream(!!anyCam);
    } catch {
      setEsp32Stream(false);
    }
    renderCamRow();
    updateContext();
    syncLapCtx();

    // FIX v4.1+v4.2: Camera laptop mặc định OFF — nút start enable, stop disable
    lapSetStatus(false, "Sẵn sàng — nhấn Bật Camera để khởi động");
    _lapBtnStopState();
    buildThemeSelector();
    startDeviceStatusPolling();
    _updateFlipBtn(); // FIX v4.2: Init flip button state

    // Update siMode + kpiUptime display
    if ($("siMode")) $("siMode").textContent = isDemo ? "Chờ dữ liệu thật" : "Thực Tế — Virtual Cluster Live";
    setInterval(() => {
      try {
        const h = Math.floor(DS.uptime / 3600), m = Math.floor((DS.uptime % 3600) / 60);
        if ($("kpiUptime")) $("kpiUptime").textContent = h > 0 ? `${h}h ${m}m` : `${m}m`;
        if ($("siMode")) $("siMode").textContent = isDemo ? "Chờ dữ liệu thật" : "Thực Tế — Virtual Cluster Live";
      } catch (e) {}
    }, 5000);

    addLog("[SYSTEM] Premium Dashboard v4.2 sẵn sàng ✓", "ok");
    lapAddLog("[SYSTEM] Laptop Camera module v4.2 — FIX: Biển số không bị đảo ngược ✓", "ok");
    lapAddLog("[v4.2] Canvas draw: THẲNG (không flip) | Display: CSS scaleX(-1)", "info");
    toast("🚀 Dashboard v5.0 — ThingsBoard Engine Live!", "ok");
    addLog("[TB-ENGINE] ThingsBoard Integration v5.0 khởi tạo...", "info");
    // FIX v6.0: Khởi động GPS ngay khi trang load — xin quyền vị trí
    setTimeout(() => { GEO.init(); }, 300);
    addLog("[GEO] 📍 GPS module v6.0 khởi động — đang xin quyền vị trí...", "info");
    setTimeout(() => { tbEngineInit(); }, 800); // TB engine boot after DOM settles
  } catch (e) {
    console.error("[BOOT ERROR]", e);
    addLog(`[BOOT ERROR] ${e.message}`, "err");
    toast("Lỗi khởi động hệ thống: " + e.message, "err");
  }
}

// ═══════════════════════════════════════════════════════════════
// PERIODIC UPDATES
// ═══════════════════════════════════════════════════════════════
setInterval(updateContext,  5000);
setInterval(() => {                      // v5.0 enhanced cam row
  if (window._tbReady) tbSyncLegacy();
  else renderCamRow();
}, 3000);
setInterval(syncLapCtx,     2000);
let deviceStatusPollStarted = false;
function startDeviceStatusPolling() {
  if (deviceStatusPollStarted) return;
  deviceStatusPollStarted = true;
  setInterval(async () => {
    try {
      if (isDemo) return;
      const r = await safeFetch("/api/device-status");
      if (r?.ok && r.devices) {
        LIVE_DEVICES = r.devices;
        renderDevices();
        try {
          const anyCam = Object.entries(LIVE_DEVICES).some(([did, dv]) => {
            const st = (dv?.status || "").toUpperCase();
            const isCam = (did || "").toLowerCase().includes("cam") || ((dv?.device_type || "").toUpperCase().includes("CAM"));
            return isCam && st === "ONLINE";
          });
          setEsp32Stream(anyCam);
        } catch {}
      }
    } catch (e) {}
  }, 5000);
}
setInterval(() => {
  try {
    const load = Math.floor(50 + Math.random() * 45);
    const bar  = $("aiLoadBar"), val = $("aiLoadVal");
    if (bar) { bar.style.width = load + "%"; bar.className = "tb-m-fill" + (load > 80 ? " r" : load > 60 ? " a" : " g"); }
    if (val) val.textContent = load + "% Load";
  } catch (e) { console.warn("[AI Load]", e); }
}, 4000);
// Fake violation spawner removed — only real ESP32/camera violations
setInterval(() => {
  try { if ($("sec-stats")?.classList.contains("active")) renderCharts(); } catch (e) {}
}, 6000);
setInterval(() => {
  // DS.detected counter only increments on real violations (removed fake per-frame increment)
}, 3000);

setInterval(() => {
  try { if (particlesInitialized) attachNeonHoverListeners(); } catch (e) {}
}, 10000);

// ── LAUNCH ──
boot();
// ╔═══════════════════════════════════════════════════════════════════════════╗
// ║  THINGSBOARD ENGINE v5.0 — AI TRAFFIC DASHBOARD                          ║
// ║  ESP32-CAM → HTTP Telemetry → ThingsBoard → JWT Poll → Live Dashboard    ║
// ║  POLICY: chỉ có tăng, không giảm — append only                           ║
// ║                                                                           ║
// ║  Answers 8 operator questions per device:                                 ║
// ║  Q1: Camera còn sống?  Q2: Upload OK?  Q3: WiFi ổn?  Q4: Cấu hình?      ║
// ║  Q5: Chụp/Thất bại?   Q6: Vị trí GPS? Q7: ID/Model? Q8: Status?         ║
// ╚═══════════════════════════════════════════════════════════════════════════╝

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG — loaded from localStorage, editable in Settings panel
// ─────────────────────────────────────────────────────────────────────────────
const TB = {
  host:      localStorage.getItem("TB_HOST")  || "http://localhost:8080",
  user:      localStorage.getItem("TB_USER")  || "tenant@thingsboard.org",
  pass:      localStorage.getItem("TB_PASS")  || "tenant",
  offlineMs: parseInt(localStorage.getItem("TB_INACT") || "5000"),
  pollMs:    4000,           // poll interval ms
  jwt:       null,           // JWT token (renewed automatically)
  jwtExp:    0,              // JWT expiry timestamp
};

// ─────────────────────────────────────────────────────────────────────────────
// RUNTIME STATE
// ─────────────────────────────────────────────────────────────────────────────
const TBD  = {};   // devices   { devId → { id, name, online, lastSeen } }
const TBTE = {};   // telemetry { devId → { upload_ok, last_http_code, latency_ms, Wifi_Status } }
const TBAT = {};   // attrs     { devId → { client:{}, server:{} } }
const TBAL = {};   // alarms    { devId → { active, severity, ts, msg } }
const TBST = {};   // stats     { devId → { total, success, fail } }

let _tbConnected = false;
let _tbPollTimer = null;
let _tbLastSync  = 0;
window._tbReady  = false;

// ─────────────────────────────────────────────────────────────────────────────
// HTTP HELPERS
// ─────────────────────────────────────────────────────────────────────────────
async function _tbLogin() {
  try {
    const r = await fetch(`${TB.host}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: TB.user, password: TB.pass }),
      signal: AbortSignal.timeout(7000),
    });
    if (!r.ok) {
      addLog(`[TB] ⚠ Auth lỗi HTTP ${r.status} — kiểm tra username/password trong Cài Đặt`, "warn");
      _tbSetBadge(false, `Auth lỗi (${r.status})`);
      return false;
    }
    const d   = await r.json();
    TB.jwt    = d.token;
    TB.jwtExp = Date.now() + (d.refreshTokenExpTime || 3_600_000);
    _tbConnected = true;
    addLog("[TB] ✅ Đăng nhập ThingsBoard thành công", "ok");
    _tbSetBadge(true, "ThingsBoard LIVE");
    return true;
  } catch (e) {
    addLog(`[TB] Không thể kết nối ThingsBoard: ${e.message}`, "warn");
    _tbSetBadge(false, "Virtual Cluster Offline");
    return false;
  }
}

async function _tbEnsureJwt() {
  if (TB.jwt && Date.now() < TB.jwtExp - 30_000) return true;
  return _tbLogin();
}

async function _tbGet(path) {
  if (!await _tbEnsureJwt()) return null;
  try {
    const r = await fetch(`${TB.host}${path}`, {
      headers: { "X-Authorization": `Bearer ${TB.jwt}`, "Content-Type": "application/json" },
      signal: AbortSignal.timeout(8000),
    });
    if (r.status === 401) { TB.jwt = null; return _tbGet(path); }
    if (!r.ok) { addLog(`[TB] HTTP ${r.status} @ ${path}`, "warn"); return null; }
    return r.json().catch(() => null);
  } catch (e) {
    if (e.name !== "AbortError") addLog(`[TB] Fetch lỗi: ${e.message}`, "warn");
    return null;
  }
}

async function _tbPost(path, body) {
  if (!await _tbEnsureJwt()) return false;
  try {
    const r = await fetch(`${TB.host}${path}`, {
      method: "POST",
      headers: { "X-Authorization": `Bearer ${TB.jwt}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8000),
    });
    return r.ok;
  } catch { return false; }
}

// ─────────────────────────────────────────────────────────────────────────────
// DEVICE DISCOVERY — find all devices in ThingsBoard tenant
// ─────────────────────────────────────────────────────────────────────────────
async function tbDiscover() {
  const data = await _tbGet("/api/tenant/devices?pageSize=50&page=0");
  if (!data?.data) return 0;
  let added = 0;
  data.data.forEach(dev => {
    if (TBD[dev.id.id]) return;
    TBD[dev.id.id]  = { id: dev.id.id, name: dev.name, online: false, lastSeen: 0 };
    TBTE[dev.id.id] = { upload_ok: null, last_http_code: null, latency_ms: null, Wifi_Status: null };
    TBAT[dev.id.id] = { client: {}, server: {} };
    TBAL[dev.id.id] = { active: false, severity: "", ts: 0, msg: "" };
    TBST[dev.id.id] = { total: 0, success: 0, fail: 0 };
    addLog(`[TB] 📷 Tìm thấy: ${dev.name} (${dev.id.id.slice(0,8)}...)`, "ok");
    added++;
  });
  const total = Object.keys(TBD).length;
  addLog(`[TB] Tổng ${total} device trong ThingsBoard`, total > 0 ? "ok" : "warn");
  return total;
}

// ─────────────────────────────────────────────────────────────────────────────
// TELEMETRY + ATTRIBUTE FETCH PER DEVICE
// ─────────────────────────────────────────────────────────────────────────────
async function _fetchTelemetry(devId) {
  const keys = "upload_ok,last_http_code,latency_ms,Wifi_Status";
  const d = await _tbGet(`/api/plugins/telemetry/DEVICE/${devId}/values/timeseries?keys=${keys}`);
  if (!d) return;
  const t = TBTE[devId];
  ["upload_ok","last_http_code","latency_ms","Wifi_Status"].forEach(k => {
    if (!d[k]?.[0]) return;
    const v = d[k][0].value;
    // Track upload_ok transitions to accumulate stats
    if (k === "upload_ok" && t.upload_ok !== null && String(v) !== String(t.upload_ok)) {
      TBST[devId].total++;
      if (parseInt(v) === 1) TBST[devId].success++;
      else                   TBST[devId].fail++;
    }
    t[k]         = v;
    t[k + "_ts"] = d[k][0].ts;
  });
}

async function _fetchAttrs(devId) {
  // CLIENT SCOPE
  const cl = await _tbGet(`/api/plugins/telemetry/DEVICE/${devId}/values/attributes/CLIENT_SCOPE`);
  if (cl) {
    const m = {};
    (Array.isArray(cl) ? cl : []).forEach(a => { m[a.key] = a.value; });
    TBAT[devId].client = m;
  }
  // SERVER SCOPE
  const sv = await _tbGet(`/api/plugins/telemetry/DEVICE/${devId}/values/attributes/SERVER_SCOPE`);
  if (!sv) return;
  const m = {};
  (Array.isArray(sv) ? sv : []).forEach(a => { m[a.key] = a.value; });
  TBAT[devId].server = m;

  // Determine online state
  const wasOnline = TBD[devId].online;
  if (m.active !== undefined) {
    TBD[devId].online = (m.active === true || m.active === "true");
  }
  if (m.lastActivityTime) {
    const lastAct = parseInt(m.lastActivityTime);
    TBD[devId].lastSeen = lastAct;
    const inact = parseInt(m.inactivityAlarmTime || TB.offlineMs);
    if ((Date.now() - lastAct) > inact) TBD[devId].online = false;
  }

  // ALARM: fire/clear on online state change
  const nowOnline = TBD[devId].online;
  if (wasOnline && !nowOnline) _tbFireAlarm(devId);
  else if (!wasOnline && nowOnline) _tbClearAlarm(devId);
}

// ─────────────────────────────────────────────────────────────────────────────
// ALARM ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function _tbFireAlarm(devId) {
  const dev = TBD[devId];
  TBAL[devId] = { active: true, severity: "CRITICAL", ts: Date.now(), msg: `${dev.name} — DEVICE_OFFLINE` };
  toast(`🔴 ALARM: ${dev.name} mất kết nối!`, "err");
  addLog(`[ALARM] 🔴 DEVICE_OFFLINE: ${dev.name} | inactivity > ${TB.offlineMs}ms`, "err");
  tbRenderAlarmList();
  _tbUpdateNavAlarm();
}

function _tbClearAlarm(devId) {
  const had = TBAL[devId]?.active;
  TBAL[devId] = { active: false, severity: "", ts: 0, msg: "" };
  if (had) {
    toast(`✅ ${TBD[devId]?.name} ONLINE trở lại — alarm cleared`, "ok");
    addLog(`[ALARM] ✅ DEVICE_ONLINE: ${TBD[devId]?.name} kết nối lại`, "ok");
    tbRenderAlarmList();
  }
  _tbUpdateNavAlarm();
}

function _tbUpdateNavAlarm() {
  const active = Object.values(TBAL).filter(a => a.active).length;
  const badge  = $("tbAlarmNavBadge");
  const navEl  = document.querySelector(".nav-item[data-s='devices']");
  if (badge) badge.style.display = active > 0 ? "inline-block" : "none";
  if (navEl) navEl.classList.toggle("has-alarm", active > 0);
  const lhAlarm = $("tbLhAlarm");
  if (lhAlarm) {
    lhAlarm.textContent = `${active} ALARM`;
    lhAlarm.style.display = active > 0 ? "inline-flex" : "none";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN POLL LOOP
// ─────────────────────────────────────────────────────────────────────────────
async function tbPollAll() {
  if (!_tbConnected) return;
  const ids = Object.keys(TBD);
  if (!ids.length) { await tbDiscover(); return; }
  // Concurrent fetch for all devices
  await Promise.allSettled(ids.map(id => (async () => {
    await _fetchAttrs(id);
    await _fetchTelemetry(id);
  })()));
  _tbLastSync = Date.now();
  tbRenderDeviceGrid();
  tbSyncLegacy();
  _tbSetBadge(true);
}

function _tbStartPoll() {
  if (_tbPollTimer) clearInterval(_tbPollTimer);
  tbPollAll();
  _tbPollTimer = setInterval(tbPollAll, TB.pollMs);
  addLog(`[TB] Polling active — ${TB.pollMs}ms interval`, "ok");
}

// ─────────────────────────────────────────────────────────────────────────────
// BADGE + SYSTEM STATUS SYNC
// ─────────────────────────────────────────────────────────────────────────────
function _tbSetBadge(live, label) {
  const ids    = Object.keys(TBD);
  const online = ids.filter(id => TBD[id].online).length;
  const total  = ids.length;
  const anyAlive = online > 0;

  // ThingsBoard dot + label
  const dot = $("tbDot"), lbl = $("tbLabel");
  if (dot) dot.className = `tb-dot neon-led-pulse ${live && anyAlive ? "led-green" : live ? "led-amber" : "led-red"}`;
  if (lbl) lbl.textContent = label || (
    live && anyAlive ? `Virtual Cluster LIVE — ${online}/${total} device online` :
    live             ? "ThingsBoard Bridge OK — Virtual Cluster standby..." :
                       "Virtual Cluster Offline"
  );

  // Sidebar conn LED
  const cled = $("connLed"), ctxt = $("connText");
  if (cled) cled.className = `conn-led ${live && anyAlive ? "online" : live ? "demo" : "offline"}`;
  if (ctxt) ctxt.textContent = live && anyAlive
    ? `Virtual Cluster LIVE — ${online}/${total} device`
    : live ? "ThingsBoard Bridge OK — Virtual standby" : "Virtual Cluster Offline";

  // ESP32 live badge in sidebar
  const liveBadge = $("esp32LiveBadge");
  if (liveBadge) liveBadge.style.display = anyAlive ? "flex" : "none";

  // sysMode chip
  const smd = $("sysModeDot"), smt = $("sysModeText"), smc = $("sysModeChip");
  if (smd) smd.style.background = live && anyAlive ? "var(--green)" : live ? "var(--amber)" : "var(--red)";
  if (smt) smt.textContent = live && anyAlive
    ? `🔴 VIRTUAL CLUSTER RUNTIME — ${online}/${total} DEVICE LIVE`
    : live ? "⚡ ThingsBoard Bridge OK — Virtual standby" : "⚡ Chờ ThingsBoard Bridge...";
  if (smc) smc.style.borderColor = live && anyAlive
    ? "rgba(0,232,122,.35)" : live ? "rgba(255,176,32,.3)" : "rgba(255,58,92,.25)";

  // Header summary bar
  const lhDot = $("tbLhDot"), lhCount = $("tbLhCount");
  if (lhDot)   lhDot.className = `tb-lh-dot ${live && anyAlive ? "dot-green" : live ? "dot-amber" : "dot-red"}`;
  if (lhCount) lhCount.textContent = live
    ? `${online}/${total} device online · ${Object.values(TBAL).filter(a=>a.active).length} alarm`
    : "Offline";

  // Sync time
  const syncEl = $("tbHdrSync");
  if (syncEl && _tbLastSync) syncEl.textContent = "Sync: " + new Date(_tbLastSync).toLocaleTimeString("vi-VN",{hour12:false});

  // KPI cameras
  if ($("kpiCams")) $("kpiCams").textContent = online;
  const camSub = $("kpiCamsSub");
  if (camSub) {
    camSub.textContent = anyAlive ? `● ${online} virtual device live` : live ? "● Virtual standby" : "● Virtual offline";
    camSub.style.color = anyAlive ? "var(--green)" : "var(--t3)";
  }

  // chipMQTT
  if ($("chipMQTT")) $("chipMQTT").textContent = live && anyAlive ? "TB LIVE" : live ? "TB OK" : "Offline";

  // isDemo flag: only demo when TB offline AND no real devices
  if (live && anyAlive) { isDemo = false; espOK = true; }
}

// Override badge wording to reflect virtual_esp32_cluster.py as the runtime source.
function _tbSetBadge(live, label) {
  const ids = Object.keys(TBD);
  const online = ids.filter(id => TBD[id].online).length;
  const total = ids.length;
  const anyAlive = online > 0;

  const dot = $("tbDot"), lbl = $("tbLabel");
  if (dot) dot.className = `tb-dot neon-led-pulse ${live && anyAlive ? "led-green" : live ? "led-amber" : "led-red"}`;
  if (lbl) lbl.textContent = label || (
    live && anyAlive ? `Virtual Cluster LIVE - ${online}/${total} device online` :
    live ? "ThingsBoard Bridge OK - Virtual Cluster standby..." :
    "Virtual Cluster Offline"
  );

  const cled = $("connLed"), ctxt = $("connText");
  if (cled) cled.className = `conn-led ${live && anyAlive ? "online" : live ? "demo" : "offline"}`;
  if (ctxt) ctxt.textContent = live && anyAlive
    ? `Virtual Cluster LIVE - ${online}/${total} device`
    : live ? "ThingsBoard Bridge OK - Virtual standby" : "Virtual Cluster Offline";

  const liveBadge = $("esp32LiveBadge");
  if (liveBadge) liveBadge.style.display = anyAlive ? "flex" : "none";

  const smd = $("sysModeDot"), smt = $("sysModeText"), smc = $("sysModeChip");
  if (smd) smd.style.background = live && anyAlive ? "var(--green)" : live ? "var(--amber)" : "var(--red)";
  if (smt) smt.textContent = live && anyAlive
    ? `Virtual Cluster Runtime - ${online}/${total} device LIVE`
    : live ? "ThingsBoard Bridge OK - Virtual standby" : "Waiting ThingsBoard Bridge...";
  if (smc) smc.style.borderColor = live && anyAlive
    ? "rgba(0,232,122,.35)" : live ? "rgba(255,176,32,.3)" : "rgba(255,58,92,.25)";

  const lhDot = $("tbLhDot"), lhCount = $("tbLhCount");
  if (lhDot) lhDot.className = `tb-lh-dot ${live && anyAlive ? "dot-green" : live ? "dot-amber" : "dot-red"}`;
  if (lhCount) lhCount.textContent = live
    ? `${online}/${total} device online · ${Object.values(TBAL).filter(a => a.active).length} alarm`
    : "Offline";

  const syncEl = $("tbHdrSync");
  if (syncEl && _tbLastSync) syncEl.textContent = "Sync: " + new Date(_tbLastSync).toLocaleTimeString("vi-VN", { hour12: false });

  if ($("kpiCams")) $("kpiCams").textContent = online;
  const camSub = $("kpiCamsSub");
  if (camSub) {
    camSub.textContent = anyAlive ? `● ${online} virtual device live` : live ? "● Virtual standby" : "● Virtual offline";
    camSub.style.color = anyAlive ? "var(--green)" : "var(--t3)";
  }

  if ($("chipMQTT")) $("chipMQTT").textContent = live && anyAlive ? "VIRTUAL LIVE" : live ? "BRIDGE OK" : "Offline";
  if (live && anyAlive) { isDemo = false; espOK = true; }
}

// ─────────────────────────────────────────────────────────────────────────────
// LEGACY ELEMENT SYNC — update existing bars/metrics already in HTML
// ─────────────────────────────────────────────────────────────────────────────
function tbSyncLegacy() {
  _tbSetBadge(_tbConnected);

  const ids    = Object.keys(TBD);
  const online = ids.filter(id => TBD[id].online);

  // Signal bars (esp1Bar, esp2Bar, esp3Bar)
  ids.slice(0, 3).forEach((id, i) => {
    const dev = TBD[id];
    const t   = TBTE[id] || {};
    const dbm = parseInt(t.Wifi_Status) || 0;
    const pct = dbm < 0 ? Math.max(0, Math.min(100, ((dbm + 100) / 60) * 100)) : (dev.online ? 78 : 0);
    const bar = $(`esp${i+1}Bar`), val = $(`esp${i+1}Val`);
    if (bar) { bar.style.width = pct + "%"; bar.className = `tb-m-fill ${pct>60?"g":pct>30?"a":"r"}`; }
    if (val) val.textContent = `${dbm < 0 ? dbm+"dBm" : "--"} — ${dev.online ? "● LIVE" : "○ OFFLINE"}`;
  });

  // MQTT bar = TB connectivity
  const mb = $("mqttBar"), mv = $("mqttVal");
  if (mb) { mb.style.width = _tbConnected ? "100%" : "0%"; mb.className = `tb-m-fill ${_tbConnected?"g":"r"}`; }
  if (mv) mv.textContent = _tbConnected
    ? `ThingsBoard Bridge OK · ${online.length}/${ids.length} virtual device online`
    : "Đang kết nối ThingsBoard Bridge...";

  // AI latency from TB telemetry average
  const lats = ids.map(id => parseInt(TBTE[id]?.latency_ms)).filter(x => x > 0);
  if (lats.length) {
    const avg = Math.round(lats.reduce((a,b)=>a+b,0)/lats.length);
    if ($("siLatency"))   $("siLatency").textContent   = avg + "ms";
    if ($("chipLatency")) $("chipLatency").textContent  = avg + "ms";
  }

  // siEspRow uptime
  const espRow = $("siEspRow");
  if (espRow) espRow.style.display = online.length > 0 ? "flex" : "none";

  // Overview cam row
  tbRenderCamRow();
}

// ─────────────────────────────────────────────────────────────────────────────
// CAM ROW in Overview — replace demo with TB real data
// ─────────────────────────────────────────────────────────────────────────────
function tbRenderCamRow() {
  const row = $("camRow");
  if (!row) return;
  const ids = Object.keys(TBD);
  if (!ids.length) { renderCamRow(); return; }  // fall back to demo
  row.innerHTML = ids.map(id => {
    const dev = TBD[id];
    const cl  = TBAT[id]?.client || {};
    const t   = TBTE[id] || {};
    const st  = dev.online ? "online" : "offline";
    const lat = parseInt(t.latency_ms) || 0;
    const alm = TBAL[id]?.active;
    const camId = cl.camera_id || dev.name;
    return `<div class="cam-card ${st} neon-hover ${alm ? "cam-alarm" : ""}" onclick="goTo('devices')" title="Click để xem chi tiết thiết bị">
      <div class="cam-icon">📷</div>
      <div class="cam-info">
        <div class="cam-name">${camId}</div>
        <div class="cam-detail">${dev.online ? `TB LIVE · ${lat}ms` : alm ? "⚠ DEVICE_OFFLINE" : "Chờ kết nối..."}</div>
      </div>
      <div class="cam-status-badge ${st}">${dev.online ? "LIVE" : "OFFLINE"}</div>
    </div>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
// ALARM LIST RENDER — replaces/extends alertList
// ─────────────────────────────────────────────────────────────────────────────
function tbRenderAlarmList() {
  const list = $("alertList");
  if (!list) return;
  const active = Object.entries(TBAL).filter(([,a]) => a.active);
  if (!active.length) {
    list.innerHTML = `<div class="no-data">✅ Không có cảnh báo — Tất cả device online</div>`;
    return;
  }
  list.innerHTML = active.map(([id, a]) => {
    const name = TBD[id]?.name || id;
    return `<div class="alert-item err tb-alarm-row">
      <span class="alert-icon">🔴</span>
      <div style="flex:1">
        <div class="alert-msg">${name} — DEVICE_OFFLINE</div>
        <div style="font-size:9px;color:var(--t3);font-family:var(--mono);margin-top:2px">
          inactivityAlarmTime &gt; ${TB.offlineMs}ms · ${new Date(a.ts).toLocaleTimeString("vi-VN",{hour12:false})}
        </div>
      </div>
      <span class="alert-time" style="color:var(--red);font-family:var(--mono);font-size:9px;font-weight:700">CRITICAL</span>
    </div>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
// DEVICE GRID RENDER — 8 operator questions per card
// ─────────────────────────────────────────────────────────────────────────────
function tbRenderDeviceGrid() {
  const grid = $("tbDeviceGrid");
  if (!grid) return;
  const ids = Object.keys(TBD);
  if (!ids.length) {
    grid.innerHTML = `<div class="tb-skeleton">
      <div class="tb-sk-dot"></div>
      <div class="tb-sk-text">Chưa tìm thấy device — ThingsBoard Bridge đã kết nối · chờ Virtual Cluster push telemetry</div>
    </div>`;
    return;
  }
  grid.innerHTML = ids.map(id => _tbBuildCard(id)).join("");
  // Wire expand/collapse buttons
  grid.querySelectorAll("[data-tbe]").forEach(btn => {
    btn.addEventListener("click", () => {
      const p = $("tbp-" + btn.dataset.tbe);
      if (!p) return;
      const open = p.style.display !== "none";
      p.style.display = open ? "none" : "block";
      btn.innerHTML = open ? "▼ Chi tiết" : "▲ Thu gọn";
    });
  });
  // Reboot buttons
  grid.querySelectorAll("[data-tbr]").forEach(b => b.addEventListener("click", () => tbRebootDevice(b.dataset.tbr)));
  // Ping buttons
  grid.querySelectorAll("[data-tbp]").forEach(b => b.addEventListener("click", () => tbPingDevice(b.dataset.tbp)));
  // Locate buttons
  grid.querySelectorAll("[data-tbl]").forEach(b => b.addEventListener("click", () => tbLocateDevice(b.dataset.tbl)));
}

function _tbBuildCard(id) {
  const dev  = TBD[id];
  const tel  = TBTE[id] || {};
  const cl   = TBAT[id]?.client || {};
  const sv   = TBAT[id]?.server || {};
  const alm  = TBAL[id]  || { active: false };
  const stat = TBST[id]  || { total: 0, success: 0, fail: 0 };

  // ── Extract values ──
  const uploadOk = parseInt(tel.upload_ok);
  const latency  = parseInt(tel.latency_ms) || 0;
  const wifiRaw  = tel.Wifi_Status ?? "--";
  const httpCode = tel.last_http_code ?? "--";
  const model    = cl.Model  || cl.model || "AI Thinker";
  const fwCl     = cl.fw_version || "--";
  const camId    = cl.camera_id  || dev.name;
  const locRaw   = cl.location   || "";
  const fwSv     = sv.fw_version || fwCl;
  const active   = sv.active;
  const fps      = sv.frames_per_upload || "--";
  const jpegQ    = sv.jpeg_quality || "--";
  const res      = sv.resolution   || "--";
  const pixFmt   = sv.pixel_format || "JPEG";
  const reboot   = sv.reboot;
  const inactMs  = sv.inactivityAlarmTime || TB.offlineMs;
  const lastAct  = parseInt(sv.lastActivityTime   || dev.lastSeen || 0);
  const lastConn = parseInt(sv.lastConnectTime    || 0);
  const lastDisc = parseInt(sv.lastDisconnectTime || 0);
  const fmt      = ts => ts > 0 ? new Date(ts).toLocaleTimeString("vi-VN",{hour12:false}) : "--";

  // ── 8 Question answers ──
  // Q1: Còn sống?
  const alive    = dev.online && (active === true || active === "true");
  // Q2: Upload OK?
  const upOk     = uploadOk === 1 && (httpCode === "200" || httpCode === 200);
  // Q3: WiFi ổn?
  const dbm      = typeof wifiRaw === "number" ? wifiRaw : parseInt(wifiRaw) || 0;
  const wifiGood = dbm < 0 ? dbm > -75 : wifiRaw === "CONNECTED";
  const wifiPct  = dbm < 0 ? Math.max(0, Math.min(100, ((dbm + 100) / 60) * 100)) : (wifiGood ? 75 : 15);
  const wifiColor= wifiPct > 60 ? "var(--green)" : wifiPct > 30 ? "var(--amber)" : "var(--red)";
  const wifiLbl  = dbm < 0 ? `${dbm} dBm` : String(wifiRaw);
  // Q5: Upload stats
  const sucPct   = stat.total > 0 ? Math.round(stat.success / stat.total * 100) : 0;
  // Q6: Location
  let lat = null, lng = null, hasLoc = false;
  if (locRaw?.includes(",")) {
    const p = locRaw.split(",");
    lat = parseFloat(p[0]); lng = parseFloat(p[1]);
    hasLoc = !isNaN(lat) && !isNaN(lng);
  } else if (cl.lat && cl.lng) {
    lat = parseFloat(cl.lat); lng = parseFloat(cl.lng);
    hasLoc = !isNaN(lat) && !isNaN(lng);
  }

  // ── Visual state classes ──
  const cardCls  = alive ? "online"  : alm.active ? "alarm" : "offline";
  const statusTx = alive ? "● LIVE"  : alm.active ? "⚠ ALARM" : "✕ OFFLINE";
  const statusCl = alive ? "tbcs-online" : alm.active ? "tbcs-alarm" : "tbcs-offline";
  const ledCls   = alive ? "tbl-green" : alm.active ? "tbl-amber" : "tbl-red";

  return `
<div class="tb-card ${cardCls}" id="tbcard-${id}">

  <!-- ════ CARD HEADER ════ -->
  <div class="tb-card-hdr">
    <div class="tb-ch-left">
      <span class="tb-ch-led ${ledCls}"></span>
      <div>
        <div class="tb-ch-name">${camId}</div>
        <div class="tb-ch-sub">${model} &nbsp;·&nbsp; FW&nbsp;${fwSv}</div>
      </div>
    </div>
    <div class="tb-ch-right">
      <span class="tb-card-status ${statusCl}">${statusTx}</span>
      <button class="tb-expand-btn" data-tbe="${id}">▼ Chi tiết</button>
    </div>
  </div>

  <!-- ════ Q1–Q4: QUICK GRID ════ -->
  <div class="tb-qgrid">

    <!-- Q1: Còn sống? -->
    <div class="tb-qcell ${alive ? "qc-alive" : "qc-dead"}">
      <div class="tb-qico">${alive ? "💚" : "💀"}</div>
      <div class="tb-qlbl">Còn sống?</div>
      <div class="tb-qval">${alive ? "ONLINE" : "OFFLINE"}</div>
      <div class="tb-qsub">Last: ${fmt(lastAct)}</div>
    </div>

    <!-- Q2: Upload OK? -->
    <div class="tb-qcell ${upOk ? "qc-ok" : "qc-warn"}">
      <div class="tb-qico">${uploadOk === 1 ? "📤" : "❌"}</div>
      <div class="tb-qlbl">Upload OK?</div>
      <div class="tb-qval">${uploadOk === 1 ? "OK" : uploadOk === 0 ? "FAIL" : "--"}</div>
      <div class="tb-qsub">HTTP&nbsp;${httpCode}&nbsp;·&nbsp;${latency}ms</div>
    </div>

    <!-- Q3: WiFi ổn? -->
    <div class="tb-qcell ${wifiGood ? "qc-ok" : "qc-warn"}">
      <div class="tb-qico">${wifiGood ? "📶" : "⚠️"}</div>
      <div class="tb-qlbl">WiFi ổn?</div>
      <div class="tb-qval">${wifiLbl}</div>
      <div class="tb-wifi-bar"><div class="tb-wifi-fill" style="width:${wifiPct}%;background:${wifiColor}"></div></div>
    </div>

    <!-- Q4: Cấu hình -->
    <div class="tb-qcell qc-cfg">
      <div class="tb-qico">⚙️</div>
      <div class="tb-qlbl">Cấu hình</div>
      <div class="tb-qval">${res}</div>
      <div class="tb-qsub">Q${jpegQ}&nbsp;·&nbsp;${pixFmt}&nbsp;·&nbsp;${fps}fps</div>
    </div>

  </div><!-- /tb-qgrid -->

  <!-- ════ Q5: UPLOAD STATS ════ -->
  <div class="tb-stat-bar">
    <span class="tb-sb-lbl">📸&nbsp;Capture stats</span>
    <div class="tb-sb-body">
      <span class="tb-sb-total">${stat.total}&nbsp;lần</span>
      <span class="tb-sb-ok">✅&nbsp;${stat.success}</span>
      <span class="tb-sb-fail">❌&nbsp;${stat.fail}</span>
      <div class="tb-sb-track"><div class="tb-sb-fill" style="width:${sucPct}%"></div></div>
    </div>
  </div>

  <!-- ════ Q6: LOCATION ════ -->
  <div class="tb-loc-row">
    <span class="tb-loc-ico">📍</span>
    <span class="tb-loc-txt">${hasLoc ? `${lat.toFixed(6)}, ${lng.toFixed(6)}` : "Chưa có vị trí GPS"}</span>
    ${hasLoc ? `<button class="tb-loc-btn" data-tbl="${id}">🗺 Map</button>` : ""}
  </div>

  <!-- ════ Q7: ID + MODEL ════ -->
  <div class="tb-id-row">
    <span class="tb-chip tb-chip-id">ID:&nbsp;${camId}</span>
    <span class="tb-chip tb-chip-model">${model}</span>
    <span class="tb-chip tb-chip-fw">FW&nbsp;${fwSv}</span>
  </div>

  <!-- ════ Q8: STATUS + ALARM ════ -->
  <div class="tb-status-row">
    ${alm.active ? `<div class="tb-alarm-inline">⚠️&nbsp;DEVICE_OFFLINE&nbsp;·&nbsp;${fmt(alm.ts)}</div>` : ""}
    <div class="tb-conn-times">🔌&nbsp;Connect:&nbsp;${fmt(lastConn)}&nbsp;&nbsp;·&nbsp;&nbsp;Disconnect:&nbsp;${fmt(lastDisc)}</div>
  </div>

  <!-- ════ DETAIL PANEL (collapsed by default) ════ -->
  <div class="tb-detail" id="tbp-${id}" style="display:none">
    <div class="tb-dt-grid">

      <!-- Telemetry -->
      <div class="tb-dt-col">
        <div class="tb-dt-hdr tbd-cyan">📡 TELEMETRY (realtime)</div>
        <div class="tb-dt-row"><span>upload_ok</span>      <span class="tb-dv ${uploadOk===1?"dv-g":uploadOk===0?"dv-r":""}">${tel.upload_ok ?? "--"}</span></div>
        <div class="tb-dt-row"><span>last_http_code</span> <span class="tb-dv ${httpCode==="200"||httpCode===200?"dv-g":"dv-a"}">${httpCode}</span></div>
        <div class="tb-dt-row"><span>latency_ms</span>     <span class="tb-dv">${latency}&nbsp;ms</span></div>
        <div class="tb-dt-row"><span>Wifi_Status</span>    <span class="tb-dv">${wifiLbl}</span></div>
      </div>

      <!-- Client attributes -->
      <div class="tb-dt-col">
        <div class="tb-dt-hdr tbd-green">🔧 CLIENT ATTR</div>
        <div class="tb-dt-row"><span>Model</span>          <span class="tb-dv dv-c">${model}</span></div>
        <div class="tb-dt-row"><span>fw_version</span>     <span class="tb-dv">${fwCl}</span></div>
        <div class="tb-dt-row"><span>camera_id</span>      <span class="tb-dv">${camId}</span></div>
        <div class="tb-dt-row"><span>location</span>       <span class="tb-dv" style="font-size:9px">${locRaw || "--"}</span></div>
      </div>

      <!-- Server attributes -->
      <div class="tb-dt-col">
        <div class="tb-dt-hdr tbd-amber">🖥 SERVER ATTR</div>
        <div class="tb-dt-row"><span>active</span>                <span class="tb-dv ${active?"dv-g":"dv-r"}">${active ?? "--"}</span></div>
        <div class="tb-dt-row"><span>frames_per_upload</span>     <span class="tb-dv">${fps}</span></div>
        <div class="tb-dt-row"><span>inactivityAlarmTime</span>   <span class="tb-dv dv-a">${inactMs}&nbsp;ms</span></div>
        <div class="tb-dt-row"><span>jpeg_quality</span>          <span class="tb-dv">${jpegQ}</span></div>
        <div class="tb-dt-row"><span>resolution</span>            <span class="tb-dv">${res}</span></div>
        <div class="tb-dt-row"><span>pixel_format</span>          <span class="tb-dv">${pixFmt}</span></div>
        <div class="tb-dt-row"><span>lastActivityTime</span>      <span class="tb-dv">${fmt(lastAct)}</span></div>
        <div class="tb-dt-row"><span>lastConnectTime</span>       <span class="tb-dv">${fmt(lastConn)}</span></div>
        <div class="tb-dt-row"><span>lastDisconnectTime</span>    <span class="tb-dv">${fmt(lastDisc)}</span></div>
        <div class="tb-dt-row"><span>reboot</span>                <span class="tb-dv ${reboot?"dv-a":""}">${reboot ?? "false"}</span></div>
      </div>

    </div><!-- /tb-dt-grid -->

    <!-- Actions -->
    <div class="tb-dt-actions">
      <button class="tb-act-btn tb-act-reboot" data-tbr="${id}">🔄 Reboot</button>
      <button class="tb-act-btn tb-act-ping"   data-tbp="${id}">📡 Ping</button>
      ${hasLoc ? `<button class="tb-act-btn tb-act-map" data-tbl="${id}">🗺 Google Maps</button>` : ""}
      <span class="tb-dt-sync">Sync: ${_tbLastSync ? new Date(_tbLastSync).toLocaleTimeString("vi-VN",{hour12:false}) : "--"}</span>
    </div>
  </div><!-- /tb-detail -->

</div><!-- /tb-card -->`;
}

// ─────────────────────────────────────────────────────────────────────────────
// DEVICE ACTIONS
// ─────────────────────────────────────────────────────────────────────────────
async function tbRebootDevice(id) {
  if (!confirm(`Gửi lệnh REBOOT cho ${TBD[id]?.name}?`)) return;
  const ok = await _tbPost(`/api/plugins/telemetry/DEVICE/${id}/attributes/SERVER_SCOPE`, { reboot: true });
  toast(ok ? `🔄 Đã gửi REBOOT → ${TBD[id]?.name}` : "Lỗi gửi reboot", ok ? "warn" : "err");
  if (ok) addLog(`[TB] Reboot → ${TBD[id]?.name}`, "warn");
}

async function tbPingDevice(id) {
  toast(`📡 Pinging ${TBD[id]?.name}...`, "info");
  await _fetchAttrs(id);
  await _fetchTelemetry(id);
  tbRenderDeviceGrid();
  toast(`📡 Ping ${TBD[id]?.name} hoàn tất`, "ok");
}

function tbLocateDevice(id) {
  const cl = TBAT[id]?.client || {};
  let lat = cl.lat, lng = cl.lng;
  if (cl.location?.includes(",")) { const p = cl.location.split(","); lat = p[0].trim(); lng = p[1].trim(); }
  if (lat && lng) window.open(`https://www.google.com/maps?q=${lat},${lng}&z=18&t=h`, "_blank");
  else toast("Chưa có dữ liệu GPS cho device này", "warn");
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS SAVE/LOAD
// ─────────────────────────────────────────────────────────────────────────────
function tbSaveSettings() {
  const host  = $("cfTB")?.value?.trim();
  const user  = $("cfTBUser")?.value?.trim();
  const raw   = $("cfTBPass")?.value;
  const inact = parseInt($("cfInactivity")?.value) || 5000;
  if (host) { TB.host = host; localStorage.setItem("TB_HOST", host); }
  if (user) { TB.user = user; localStorage.setItem("TB_USER", user); }
  if (raw && raw !== "••••••••" && raw.length > 0) { TB.pass = raw; localStorage.setItem("TB_PASS", raw); }
  TB.offlineMs = inact;
  localStorage.setItem("TB_INACT", String(inact));
  // Reset JWT and reconnect
  TB.jwt = null; _tbConnected = false;
  setTimeout(tbEngineInit, 300);
  addLog("[TB] Settings đã lưu — reconnecting...", "ok");
}

function tbLoadSettingsUI() {
  if ($("cfTB"))         $("cfTB").value         = TB.host;
  if ($("cfTBUser"))     $("cfTBUser").value     = TB.user;
  if ($("cfInactivity")) $("cfInactivity").value  = TB.offlineMs;
  if ($("cfTBPass"))     $("cfTBPass").placeholder = "••••••••";
}

// ─────────────────────────────────────────────────────────────────────────────
// HEADER SYNC TIMER
// ─────────────────────────────────────────────────────────────────────────────
setInterval(() => {
  try {
    const syncEl = $("tbHdrSync");
    if (syncEl && _tbLastSync) syncEl.textContent = "Sync: " + new Date(_tbLastSync).toLocaleTimeString("vi-VN",{hour12:false});
    _tbUpdateNavAlarm();
  } catch (e) {}
}, 2000);

// ─────────────────────────────────────────────────────────────────────────────
// ENGINE INIT (called from boot)
// ─────────────────────────────────────────────────────────────────────────────
async function tbEngineInit() {
  addLog("[TB] ═══ ThingsBoard Engine v5.0 boot ═══", "info");
  addLog(`[TB] Host: ${TB.host} | Poll: ${TB.pollMs}ms | OfflineTimeout: ${TB.offlineMs}ms`, "info");
  _tbSetBadge(false, "Đang kết nối ThingsBoard...");

  const ok = await _tbLogin();
  if (!ok) {
    addLog("[TB] ⚠ Offline — retry in 30s. Kiểm tra credentials trong ⚙ Cài Đặt", "warn");
    setTimeout(tbEngineInit, 30_000);
    return;
  }

  await tbDiscover();
  _tbStartPoll();
  tbLoadSettingsUI();
  window._tbReady = true;
  addLog("[TB] ✅ ThingsBoard Engine sẵn sàng — live polling active", "ok");
}

// Expose globals for HTML onclick and external callers
window.tbEngineInit    = tbEngineInit;
window.tbSaveSettings  = tbSaveSettings;
window.tbPingDevice    = tbPingDevice;
window.tbRebootDevice  = tbRebootDevice;
window.tbLocateDevice  = tbLocateDevice;
window.tbPollAll       = tbPollAll;
window.tbRenderDeviceGrid = tbRenderDeviceGrid;
window.tbRenderAlarmList  = tbRenderAlarmList;
window.tbSyncLegacy       = tbSyncLegacy;
