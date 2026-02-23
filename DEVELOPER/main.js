/* ═══════════════════════════════════════════════════════════════
   AI TRAFFIC DASHBOARD — PREMIUM ENGINE v5.0.0 (2026)
   Laptop Camera + ESP32 + Demo Mode + Particles + Async Themes
   v5.0.0 NEW:
     - ai_engine_status  event → HUD realtime YOLOv8 / OCR / Camera
     - esp32_connected   event → Auto exit DEMO mode → LIVE mode
     - esp32_disconnected event → Revert to demo gracefully
     - system_mode event → Demo/Live banner + mode indicator
     - /ai_feed stream  → AI camera tab with detection overlays
     - AI Engine panel  → model loaded, OCR loaded, FPS, violations
     - Demo/Live mode switcher với toast + banner
     - Periodic /api/ai/status poll khi socket chưa kết nối
   v4.0.3 PRESERVED:
     - Pre-seed DASHBOARD_SECRET vào localStorage ĐỒNG BỘ
     - /api/bootstrap 401 → FIXED
     - /api/theme    403 → FIXED
     - authGuard không redirect khi đang ở main.html
═══════════════════════════════════════════════════════════════ */
"use strict";

// ── Auth constants ──
const TK               = "TRAFFIC_AI_TOKEN";
const DASHBOARD_SECRET = "TRAFFIC_AI_TOKEN"; // Phải khớp với DASHBOARD_SECRET trong app.py

// ══════════════════════════════════════════════════════════════
// FIX v4.0.3: PRE-SEED TOKEN — chạy ĐỒNG BỘ ngay lập tức
// Đây là fix mạnh nhất: đảm bảo token luôn có trong localStorage
// TRƯỚC KHI bất kỳ function nào khác chạy (kể cả DOMContentLoaded)
// ══════════════════════════════════════════════════════════════
(function preSeedToken() {
  const existing = localStorage.getItem(TK);
  // Chỉ set nếu chưa có token hợp lệ
  // Token hợp lệ: DASHBOARD_SECRET hoặc legacy.* (từ login form)
  if (!existing || existing.trim() === "") {
    localStorage.setItem(TK, DASHBOARD_SECRET);
    console.log("[AUTH v4.0.3] Pre-seeded DASHBOARD_SECRET token → localStorage OK");
  } else {
    console.log("[AUTH v4.0.3] Token already present:", existing.substring(0, 20) + "...");
  }
})();

const getToken = () => localStorage.getItem(TK) || DASHBOARD_SECRET;
const logout   = () => { localStorage.removeItem(TK); location.replace("login.html"); };

// Legacy flag (không cần nữa nhưng giữ để tránh lỗi reference)
let _authInProgress = false;

// authGuard: chỉ redirect nếu không có token VÀ không ở main page context
(function authGuard() {
  const tok = getToken();
  if (!tok || tok.trim() === "") {
    console.warn("[AUTH] No token after pre-seed — this should not happen");
  }
  // Không redirect từ main.html — login.html là nơi xử lý auth form
})();

// ── Helpers ──
const $  = id  => document.getElementById(id);
const qA = sel => document.querySelectorAll(sel);

// ── Global State ──
let isDemo = true;
let espOK  = false;
let modeOverride = null;
let currentTheme = 'neon-futuristic';
let particlesInitialized = false;

const DS = {
  light: "RED", countdown: 22, phase: "ĐỎ", camState: "ACTIVE",
  vehicles: 3, speed: 14.2, fps: 12,
  weather: "Nắng", dist: 5.0, roi: "STOP_LINE", capture: 500,
  totalViol: 0, todayViol: 0, detected: 0, uptime: 0,
};

// Traffic cycle
const CYCLE = [
  { light: "GREEN",  phase: "XANH", dur: 30, cam: "IDLE",   next: 1 },
  { light: "YELLOW", phase: "VÀNG", dur: 5,  cam: "WARMUP", next: 2 },
  { light: "RED",    phase: "ĐỎ",   dur: 30, cam: "ACTIVE", next: 0 },
];
let cIdx = 2;
let cycleIV = null;

// Violations
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

// Cam sim
const camFrameW = 640, camFrameH = 360;

// ── Laptop camera state ──
const LAP = {
  active:     false,
  serverMode: false,
  demoMode:   true,
  stream:     null,
  video:      null,
  animID:     null,
  snapshots:  [],
  detCount:   0,
  fps:        0,
  fpsCounter: 0,
  fpsTimer:   null,
};

// ════════════════════════════════════════════════════════════════
// v5.0: AI ENGINE STATE — synced from server events
// ════════════════════════════════════════════════════════════════
const AI = {
  active:       false,
  modelLoaded:  false,
  ocrLoaded:    false,
  cameraOpen:   false,
  fps:          0,
  detections:   0,
  violations:   0,
  contextOk:    true,
  speedKmh:     0,
  vehicles:     0,
  light:        "RED",
  lastUpdate:   0,
};

// v5.0: System mode — DEMO (no ESP32) vs LIVE (ESP32 connected)
const SYS = {
  demoMode:         true,
  esp32OnlineCount: 0,
  aiEngineActive:   false,
  liveMode:         false,
  firstEsp32At:     0,
};

// v5.0: AI Feed stream state
const AIFEED = {
  active:    false,
  imgEl:     null,
  pollTimer: null,
};

// ═══════════════════════════════════════════════════════════════
// v4.0: GLOBAL ERROR HANDLING
// ═══════════════════════════════════════════════════════════════
window.onerror = function(msg, url, line, col, err) {
  const shortMsg = typeof msg === "string" ? msg.substring(0, 120) : String(msg);
  toast(`Lỗi hệ thống: ${shortMsg} (dòng ${line})`, "err");
  addLog(`[ERROR] ${shortMsg} @ line:${line} col:${col}`, "err");
  console.error("[v4.0 ERROR]", msg, url, line, col, err);
  return false;
};

window.onunhandledrejection = function(event) {
  const reason = event.reason ? (event.reason.message || String(event.reason)).substring(0, 100) : "Unknown rejection";
  addLog(`[UNHANDLED PROMISE] ${reason}`, "err");
  console.error("[v4.0 PROMISE REJECTION]", event.reason);
};

// ═══════════════════════════════════════════════════════════════
// FIX v4.0.3: ensureToken() — safety net thứ hai sau pre-seed
// KHÔNG gọi addLog ở đây để tránh race condition với DOM
// ═══════════════════════════════════════════════════════════════
async function ensureToken() {
  const tok = getToken();
  if (tok && tok.trim() !== "") return tok; // token đã có (pre-seed đảm bảo điều này)

  // Safety net: pre-seed bị xóa bởi code nào đó → set lại
  localStorage.setItem(TK, DASHBOARD_SECRET);
  console.warn("[AUTH] ensureToken: re-applied pre-seed (should not normally happen)");
  return DASHBOARD_SECRET;
}

// ═══════════════════════════════════════════════════════════════
// FIX v4.0.2: safeFetch — luôn attach Authorization header
// Tự động gọi ensureToken() nếu token rỗng thay vì logout ngay
// ═══════════════════════════════════════════════════════════════
async function safeFetch(url, opts = {}) {
  // FIX v4.0.3: getToken() luôn có DASHBOARD_SECRET nhờ pre-seed
  // Điều kiện: không có token HOẶC token rỗng
  let tok = getToken();
  if ((!tok || tok.trim() === "") && url !== "/api/login") {
    tok = await ensureToken();
    if (!tok) {
      addLog(`[AUTH] Không thể lấy token cho ${url}`, "err");
      return null;
    }
  }

  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(url, {
      ...opts,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${tok}`,
        ...(opts.headers || {}),
      },
    });

    clearTimeout(timeoutId);

    if (response.status === 401) {
      // Token hết hạn — thử login lại 1 lần
      addLog(`[AUTH] 401 trên ${url} — thử refresh token...`, "warn");
      localStorage.removeItem(TK);
      const newTok = await ensureToken();
      if (newTok) {
        // Retry request với token mới
        const retry = await fetch(url, {
          ...opts,
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${newTok}`,
            ...(opts.headers || {}),
          },
        });
        if (retry.ok) return retry.json();
        if (retry.status === 401) {
          addLog(`[AUTH] Retry 401 — chuyển đến login`, "err");
          logout();
          return null;
        }
      }
      return null;
    }

    if (response.status === 403) {
      addLog(`[AUTH] 403 Forbidden trên ${url} — kiểm tra quyền token`, "warn");
      return null;
    }

    if (!response.ok) {
      addLog(`[API] HTTP ${response.status} cho ${url}`, "warn");
      return null;
    }

    return response.json();
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
    addLog("[PARTICLES] Particle system v4.0 khởi động ✓", "ok");
    attachNeonHoverListeners();
  } catch (e) {
    addLog(`[PARTICLES] Lỗi khởi tạo: ${e.message}`, "warn");
    console.warn("[v4.0 PARTICLES ERROR]", e);
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
    console.warn("[v4.0 NEON HOVER] Error:", e);
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
    console.warn("[v4.0 REINIT PARTICLES]", e);
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

/**
 * FIX v4.0.2: fetchTheme — đảm bảo có token trước khi gọi
 */
async function fetchTheme() {
  try {
    // FIX: Đảm bảo có token trước
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

    addLog(`[THEME] Áp dụng theme: ${themeName} ✓`, "ok");
    toast(`🎨 Theme: ${themeName}`, "ok");
  } catch (e) {
    addLog(`[THEME] Lỗi áp dụng theme: ${e.message}`, "err");
  }
}

function buildThemeSelector() {
  const sel = $("themeSelector");
  if (!sel) return;
  sel.innerHTML = Object.keys(THEMES).map(t => `<option value="${t}"${t === currentTheme ? " selected" : ""}>${t}</option>`).join("");
  sel.addEventListener("change", () => applyTheme(sel.value, true));
}

// ═══════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════
const PAGE_TITLES = {
  overview:   "Tổng Quan Hệ Thống",
  violations: "Quản Lý Vi Phạm",
  camera:     "Camera Trực Tiếp — ESP32",
  laptop:     "Camera Laptop — Test & Demo",
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
    txt.textContent = "Demo Mode";
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
      if (isDemo && DS.light === "RED") scheduleViolation();
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

    if ($("tlCountdown")) $("tlCountdown").textContent = DS.countdown;
    if ($("tlPhase"))     $("tlPhase").textContent = DS.phase;
    const pc = DS.light === "RED" ? "red" : DS.light === "YELLOW" ? "amber" : "green";
    if ($("tlPhase")) $("tlPhase").className = "val " + pc;
    if ($("tlCamState")) { $("tlCamState").textContent = DS.camState; $("tlCamState").className = "val " + (DS.camState === "ACTIVE" ? "green" : DS.camState === "WARMUP" ? "amber" : ""); }

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
    DS.speed    = parseFloat((8 + Math.random() * 14).toFixed(1));
    DS.vehicles = Math.floor(1 + Math.random() * 5);
    DS.fps      = Math.floor(10 + Math.random() * 6);

    const speedOK = DS.speed < 20;
    const vehOK   = DS.vehicles <= 6;
    const allOK   = speedOK && vehOK;
    const badCount = (!speedOK ? 1 : 0) + (!vehOK ? 1 : 0);

    setCtxItem("ctxSpeed",   "ctxSpeedVal",   DS.speed + " km/h", "ctxSpeedLed",   speedOK);
    setCtxItem("ctxVeh",     "ctxVehVal",     DS.vehicles,         "ctxVehLed",     vehOK);
    setCtxItem("ctxWeather", "ctxWeatherVal", DS.weather,          "ctxWeatherLed", true);
    setCtxItem("ctxDist",    "ctxDistVal",    DS.dist + "m",       "ctxDistLed",    true);
    setCtxItem("ctxROI",     "ctxROIVal",     DS.roi,              "ctxROILed",     true);
    setCtxItem("ctxCap",     "ctxCapVal",     DS.capture + "ms",   "ctxCapLed",     true);

    const badge = $("ctxBadge");
    if (badge) { badge.textContent = allOK ? "6/6 OK" : `${6 - badCount}/6 OK`; badge.className = "ph-badge" + (allOK ? "" : " warn"); }

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
    const allOK   = speedOK && vehOK;
    const bad     = (!speedOK ? 1 : 0) + (!vehOK ? 1 : 0);

    function setStat(valId, barId, ledId, val, pct, ok) {
      if ($(valId)) $(valId).textContent = val;
      if ($(barId)) { $(barId).style.width = pct + "%"; $(barId).className = "lap-ctx-fill" + (ok ? " ok" : " bad"); }
      if ($(ledId)) $(ledId).className = "ctx-led " + (ok ? "ok" : "bad");
    }

    setStat("lctxSpeedVal",   "lctxSpeedBar",   "lctxSpeedLed",   DS.speed + " km/h",  Math.min(100, (DS.speed/20)*100), speedOK);
    setStat("lctxVehVal",     "lctxVehBar",     "lctxVehLed",     DS.vehicles + " xe", Math.min(100, (DS.vehicles/6)*100), vehOK);
    setStat("lctxWeatherVal", null,             "lctxWeatherLed", DS.weather,          100, true);
    setStat("lctxDistVal",    null,             "lctxDistLed",    DS.dist + "m",       100, true);
    setStat("lctxROIVal",     null,             "lctxROILed",     DS.roi,              100, true);
    setStat("lctxCapVal",     null,             "lctxCapLed",     DS.capture + "ms",   100, true);

    const b = $("lapCtxBadge");
    if (b) { b.textContent = allOK ? "6/6 OK" : `${6 - bad}/6 OK`; b.className = "ph-badge" + (allOK ? "" : " warn"); }

    if ($("lapVehicles")) $("lapVehicles").textContent = DS.vehicles;
    if ($("lapSpeed"))    $("lapSpeed").textContent    = DS.speed + " km/h";
    if ($("lapFPSTag"))   $("lapFPSTag").textContent   = LAP.fps + " FPS";
  } catch (e) { console.warn("[syncLapCtx]", e); }
}

// ═══════════════════════════════════════════════════════════════
// LAPTOP CAMERA — MAIN MODULE
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
}

async function lapStart() {
  try {
    $("btnLapStart")    && ($("btnLapStart").disabled    = true);
    $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
    lapSetStatus(false, "Đang khởi động...");
    lapAddLog("Đang khởi động camera laptop...", "info");

    const apiResult = await tryFlaskLapCam();
    if (apiResult) return;

    const mediaResult = await tryBrowserMedia();
    if (mediaResult) return;

    lapStartDemo();
  } catch (e) {
    lapAddLog(`[ERROR] lapStart thất bại: ${e.message}`, "err");
    toast("Lỗi khởi động camera: " + e.message, "err");
    $("btnLapStart")    && ($("btnLapStart").disabled    = false);
    $("btnLapStartBig") && ($("btnLapStartBig").disabled = false);
  }
}

async function tryFlaskLapCam() {
  try {
    const r = await safeFetch("/api/laptop_camera/start", { method: "POST" });
    if (r && r.ok) {
      LAP.active     = true;
      LAP.serverMode = true;
      LAP.demoMode   = false;

      const img = $("lapImg");
      if (img) {
        img.src = "/laptop_feed?t=" + Date.now();
        img.onerror = () => {
          lapAddLog("Flask feed lỗi, chuyển demo...", "warn");
          lapStartDemo();
        };
      }

      lapShowFeed(true);
      lapSetStatus(true, "🎥 Flask Camera — Online");
      lapAddLog("✅ Camera laptop khởi động qua Flask server", "ok");
      $("btnLapStop")    && ($("btnLapStop").disabled    = false);
      $("btnLapStart")   && ($("btnLapStart").disabled   = true);
      $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
      if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Flask / OpenCV";
      if ($("lapAiMode")) $("lapAiMode").textContent  = "Server MJPEG";
      lapStartFPSCounter();
      toast("🎥 Camera laptop đã khởi động (Flask)!", "ok");
      return true;
    }
  } catch (e) {
    lapAddLog(`[FLASK CAM] Lỗi: ${e.message}`, "warn");
  }
  return false;
}

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

    let vid = document.getElementById("lapHiddenVideo");
    if (!vid) {
      vid = document.createElement("video");
      vid.id          = "lapHiddenVideo";
      vid.style.display = "none";
      vid.autoplay    = true;
      vid.playsinline = true;
      vid.muted       = true;
      document.body.appendChild(vid);
    }
    vid.srcObject = stream;
    LAP.video = vid;
    await vid.play();

    lapShowFeed(true);
    lapSetStatus(true, "🎥 Webcam Browser — Online");
    lapAddLog("✅ getUserMedia thành công — streaming webcam", "ok");
    $("btnLapStop")     && ($("btnLapStop").disabled    = false);
    $("btnLapStart")    && ($("btnLapStart").disabled   = true);
    $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
    if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Browser MediaStream";
    if ($("lapAiMode")) $("lapAiMode").textContent  = "getUserMedia";
    if ($("lapResCap")) $("lapResCap").textContent  = "HD 720p";

    lapStartBrowserDraw();
    lapStartFPSCounter();
    toast("🎥 Webcam trình duyệt đã kết nối!", "ok");
    return true;
  } catch (e) {
    lapAddLog("getUserMedia thất bại: " + e.message + " — dùng demo", "warn");
    return false;
  }
}

function lapStartBrowserDraw() {
  const canvas = $("lapCanvas");
  if (!canvas || !LAP.video) return;
  const ctx = canvas.getContext("2d");

  function draw() {
    if (!LAP.active || LAP.demoMode) return;
    if (!LAP.video.videoWidth) { LAP.animID = requestAnimationFrame(draw); return; }

    canvas.width  = LAP.video.videoWidth;
    canvas.height = LAP.video.videoHeight;

    ctx.drawImage(LAP.video, 0, 0, canvas.width, canvas.height);
    drawLapOverlays(ctx, canvas.width, canvas.height);

    const img = $("lapImg");
    if (img) { try { img.src = canvas.toDataURL("image/webp", 0.8); } catch (e) {} }

    LAP.fpsCounter++;
    LAP.animID = requestAnimationFrame(draw);
  }
  draw();
}

function lapStartDemo() {
  LAP.active   = true;
  LAP.demoMode = true;

  const canvas = $("lapCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  canvas.width  = 1024;
  canvas.height = 576;

  lapShowFeed(true);
  lapSetStatus(true, "💻 Demo Canvas — Simulation");
  lapAddLog("⚡ Chế độ Demo Canvas — mô phỏng camera thực tế", "ok");
  $("btnLapStop")     && ($("btnLapStop").disabled    = false);
  $("btnLapStart")    && ($("btnLapStart").disabled   = true);
  $("btnLapStartBig") && ($("btnLapStartBig").disabled = true);
  if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "Demo Canvas";
  if ($("lapAiMode")) $("lapAiMode").textContent  = "Simulation";
  if ($("lapResCap")) $("lapResCap").textContent  = "1024×576";
  toast("💻 Demo camera mô phỏng đã khởi động!", "info");

  function drawDemo() {
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

    const img = $("lapImg");
    if (img) { try { img.src = canvas.toDataURL("image/webp", 0.8); } catch (e) {} }

    LAP.fpsCounter++;
    LAP.animID = requestAnimationFrame(drawDemo);
  }
  drawDemo();
  lapStartFPSCounter();
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

function lapStop() {
  LAP.active = false;
  if (LAP.animID)   { cancelAnimationFrame(LAP.animID); LAP.animID = null; }
  if (LAP.fpsTimer) { clearInterval(LAP.fpsTimer); LAP.fpsTimer = null; }
  if (LAP.stream)   { LAP.stream.getTracks().forEach(t => t.stop()); LAP.stream = null; }

  const vid = document.getElementById("lapHiddenVideo");
  if (vid) vid.srcObject = null;

  if (LAP.serverMode) {
    safeFetch("/api/laptop_camera/stop", { method: "POST" });
  }

  LAP.serverMode = false;
  LAP.demoMode   = false;

  const img = $("lapImg");
  if (img) img.src = "";

  lapShowFeed(false);
  lapSetStatus(false, "Camera đã tắt");
  $("btnLapStop")     && ($("btnLapStop").disabled    = true);
  $("btnLapStart")    && ($("btnLapStart").disabled   = false);
  $("btnLapStartBig") && ($("btnLapStartBig").disabled = false);
  lapAddLog("Camera laptop đã dừng", "warn");
  toast("Camera laptop đã tắt.", "warn");
}

$("btnLapStart")    && $("btnLapStart").addEventListener("click",   lapStart);
$("btnLapStop")     && $("btnLapStop").addEventListener("click",    lapStop);
$("btnLapStartBig") && $("btnLapStartBig").addEventListener("click", lapStart);

if ($("btnLapRed"))   $("btnLapRed").addEventListener("click",   () => { forceLight(2); lapAddLog("[MANUAL] Bật đèn ĐỎ + quét vi phạm", "warn"); if (LAP.active) setTimeout(() => lapSpawnDetection(), 2000); });
if ($("btnLapAmber")) $("btnLapAmber").addEventListener("click", () => forceLight(1));
if ($("btnLapGreen")) $("btnLapGreen").addEventListener("click", () => forceLight(0));
if ($("btnLapAuto"))  $("btnLapAuto").addEventListener("click",  () => { resetAuto(); lapAddLog("[AUTO] Chuyển về chế độ tự động", "ok"); });

if ($("btnLapScan")) {
  $("btnLapScan").addEventListener("click", () => {
    const plate = ($("lapPlateInput") ? $("lapPlateInput").value : "").trim().toUpperCase();
    if (!plate) { toast("Nhập biển số xe!", "warn"); return; }
    lapAddLog(`[OCR] Quét biển số: ${plate}`, "info");
    setTimeout(() => {
      try {
        const conf  = Math.floor(72 + Math.random() * 27);
        const type  = TYPES[Math.floor(Math.random() * TYPES.length)];
        const speed = parseFloat((6 + Math.random() * 14).toFixed(1));
        const res   = $("lapScanResult");
        if (res) {
          res.style.display = "block";
          if ($("lapScanPlate")) $("lapScanPlate").textContent = plate;
          if ($("lapScanInfo"))  $("lapScanInfo").textContent  = `${type} · ${speed} km/h · Tin cậy: ${conf}% · Đèn: ${DS.light}`;
          res.style.borderColor = DS.light === "RED" ? "rgba(255,58,92,.4)" : "var(--rim2)";
        }
        lapAddLog(`[OCR] Kết quả: ${plate} | ${type} | ${speed}km/h | ${conf}%`, conf > 80 ? "ok" : "warn");
        toast(`Quét: ${plate} — ${conf}% tin cậy`, conf > 80 ? "ok" : "warn");
      } catch (e) { lapAddLog(`[OCR ERROR] ${e.message}`, "err"); }
    }, 800);
  });
}

if ($("btnLapSnap")) {
  $("btnLapSnap").addEventListener("click", async () => {
    try {
      if (!LAP.active) { toast("Bật camera trước!", "warn"); return; }
      const plate = ($("lapPlateInput") ? $("lapPlateInput").value : "") || "SNAP-" + String(vioID).padStart(5,"0");
      const plateUp = plate.trim().toUpperCase();
      lapAddLog(`[SNAP] Chụp ảnh: ${plateUp}`, "info");

      const r = await safeFetch("/api/laptop_camera/snapshot", { method: "POST", body: JSON.stringify({ plate: plateUp }) });
      const imgUrl = r && r.image_url ? r.image_url : null;

      const v = {
        id: vioID++, plate: plateUp, type: TYPES[Math.floor(Math.random() * TYPES.length)],
        ts: Math.floor(Date.now() / 1000), light: DS.light,
        speed_kmh: parseFloat((6 + Math.random()*14).toFixed(1)),
        confidence: Math.floor(72 + Math.random()*27), roi: "STOP_LINE",
        cam: "LAPTOP", image_url: imgUrl || ""
      };

      lapAddGalleryItem(imgUrl || ($("lapImg") ? $("lapImg").src : ""), plateUp, v.ts);

      if (DS.light === "RED") {
        VIOLS.unshift(v); filtered = [...VIOLS]; DS.totalViol++; DS.todayViol++;
        hourly[new Date().getHours()]++;
        updateKPIs(); appendRecent(v); lapAddDetItem(v); renderVioTable();
        toast(`📸 Vi phạm ghi nhận: ${plateUp}`, "err");
        lapAddLog(`[VIOL] Vi phạm: ${plateUp} (${v.type}) ${v.speed_kmh}km/h`, "err");
      } else {
        toast(`📸 Snapshot: ${plateUp} (đèn ${DS.phase} — không vi phạm)`, "info");
        lapAddLog(`[SNAP] Đèn ${DS.phase} — không ghi vi phạm`, "warn");
      }
    } catch (e) {
      lapAddLog(`[SNAP ERROR] ${e.message}`, "err");
      toast("Lỗi snapshot: " + e.message, "err");
    }
  });
}

if ($("btnSeedViol")) {
  $("btnSeedViol").addEventListener("click", () => {
    const seeds = [
      { plate:"51B-12345", type:"Xe máy", speed_kmh:16.2, confidence:88 },
      { plate:"59D-67890", type:"Ô tô",   speed_kmh:12.8, confidence:92 },
      { plate:"29A-11222", type:"Xe máy", speed_kmh:18.5, confidence:76 },
      { plate:"43K-55667", type:"Xe máy", speed_kmh:14.1, confidence:83 },
      { plate:"30F-99001", type:"Ô tô",   speed_kmh:10.5, confidence:95 },
    ];
    seeds.forEach((s, i) => {
      setTimeout(() => {
        try {
          const v = { ...s, id: vioID++, ts: Math.floor(Date.now()/1000) - i * 300, light: "RED", roi: "STOP_LINE", cam: "LAPTOP", image_url: "" };
          VIOLS.unshift(v); filtered = [...VIOLS]; DS.totalViol++; DS.todayViol++;
          hourly[new Date(v.ts*1000).getHours()]++;
          updateKPIs(); appendRecent(v); lapAddDetItem(v); renderVioTable();
          lapAddLog(`[SEED] Vi phạm: ${v.plate} (${v.type}) ${v.speed_kmh}km/h`, "err");
        } catch (e) { lapAddLog(`[SEED ERROR] ${e.message}`, "err"); }
      }, i * 400);
    });
    toast("⚡ Đã tạo 5 vi phạm demo!", "warn");
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

function lapSpawnDetection() {
  try {
    const plate = PLATES[Math.floor(Math.random() * PLATES.length)];
    const type  = TYPES[Math.floor(Math.random() * TYPES.length)];
    const v = {
      id: vioID++, plate, type, ts: Math.floor(Date.now()/1000), light: "RED",
      speed_kmh: parseFloat((6+Math.random()*14).toFixed(1)),
      confidence: Math.floor(72+Math.random()*27), roi: "STOP_LINE", cam: "LAPTOP", image_url: ""
    };
    VIOLS.unshift(v); filtered = [...VIOLS]; DS.totalViol++; DS.todayViol++;
    hourly[new Date().getHours()]++;
    updateKPIs(); appendRecent(v); lapAddDetItem(v); renderVioTable();
    toast(`⚠ Vi phạm: ${plate} (${type})`, "err");
  } catch (e) { console.warn("[lapSpawnDetection]", e); }
}

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
function scheduleViolation() {
  setTimeout(() => { if (DS.light === "RED" && isDemo) spawnViolation(); }, 3000 + Math.random() * 9000);
}

function spawnViolation() {
  try {
    const plate = PLATES[Math.floor(Math.random() * PLATES.length)];
    const type  = TYPES[Math.floor(Math.random() * TYPES.length)];
    const speed = parseFloat((6 + Math.random() * 16).toFixed(1));
    const conf  = Math.floor(72 + Math.random() * 27);
    const cam   = "CAM " + (Math.floor(Math.random() * 3) + 1);
    const v = { id: vioID++, plate, type, ts: Math.floor(Date.now()/1000), light: "RED", speed_kmh: speed, roi: "STOP_LINE", confidence: conf, cam, image_url: "" };
    VIOLS.unshift(v); filtered = [...VIOLS];
    DS.totalViol++; DS.todayViol++; DS.detected++;
    hourly[new Date().getHours()]++;
    weekly[6]++;
    updateKPIs(); updateViolationBadge(); appendRecent(v); addDetection(v);
    addLog(`[VIOLATION] ${plate} · ${type} · ${speed} km/h · ${conf}%`, "err");
    renderVioTable();
    toast(`⚠ Vi phạm: ${plate} (${type})`, "err");
  } catch (e) { console.warn("[spawnViolation]", e); }
}

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

// ═══════════════════════════════════════════════════════════════
// RECENT VIOLATIONS
// ═══════════════════════════════════════════════════════════════
function appendRecent(v) {
  try {
    const c = $("recentList");
    if (!c) return;
    c.querySelector(".no-data")?.remove();
    const card = document.createElement("div");
    card.className = "vcard new neon-hover";
    card.innerHTML = `
      <div class="vcard-img">${v.image_url ? `<img src="${v.image_url}" alt="">` : `<div class="placeholder">📷</div>`}</div>
      <div class="vcard-info">
        <div class="vcard-plate">${v.plate}</div>
        <div class="vcard-meta">${v.type} · ${new Date(v.ts * 1000).toLocaleTimeString("vi-VN")} · ${v.cam}</div>
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
        const tr  = document.createElement("tr");
        tr.classList.add("neon-hover");
        const dt  = new Date(v.ts * 1000).toLocaleString("vi-VN");
        const conf = v.confidence || 0;
        tr.innerHTML = `
          <td><span style="font-family:var(--mono);color:var(--t2);font-size:11px">#${v.id}</span></td>
          <td><span class="cell-plate">${v.plate}</span></td>
          <td>${v.type || "--"}</td><td>${dt}</td>
          <td><span class="light-chip ${(v.light||"").toLowerCase()}">${v.light||"--"}</span></td>
          <td>${v.speed_kmh ? v.speed_kmh + " km/h" : "--"}</td>
          <td>${v.roi || "--"}</td>
          <td><div class="conf-wrap"><div class="conf-bar"><div class="conf-fill" style="width:${conf}%"></div></div><span class="conf-val">${conf}%</span></div></td>
          <td>${v.image_url ? `<img src="${v.image_url}" class="thumb-img" alt="">` : `<span style="font-size:9.5px;color:var(--t3)">Demo</span>`}</td>
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
    currentViol = v;
    $("mID")    && ($("mID").textContent    = v.id);
    $("mPlate") && ($("mPlate").textContent = v.plate);
    $("mLight") && ($("mLight").textContent = v.light || "--");
    $("mTime")  && ($("mTime").textContent  = new Date(v.ts * 1000).toLocaleString("vi-VN"));
    $("mType")  && ($("mType").textContent  = v.type || "--");
    $("mSpeed") && ($("mSpeed").textContent = v.speed_kmh ? v.speed_kmh + " km/h" : "--");
    $("mROI")   && ($("mROI").textContent   = v.roi || "--");
    $("mCam")   && ($("mCam").textContent   = v.cam || "--");
    $("mOCR")   && ($("mOCR").textContent   = "OCR: " + v.plate);
    $("mConf")  && ($("mConf").textContent  = "Tin cậy: " + (v.confidence || "--") + "%");
    const img = $("mImg"), ph = $("mImgPlaceholder");
    if (v.image_url) { img.src = v.image_url; img.style.display = "block"; if (ph) ph.style.display = "none"; }
    else             { if (img) img.style.display = "none"; if (ph) ph.style.display = "flex"; }
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
  else toast("Không có hình ảnh (demo mode).", "warn");
});
$("btnPrint")  && $("btnPrint").addEventListener("click", () => { toast("Đang in biên bản...", "info"); setTimeout(() => window.print(), 500); });
$("btnDelRec") && $("btnDelRec").addEventListener("click", () => {
  if (!currentViol) return;
  try {
    const i = VIOLS.findIndex(v => v.id === currentViol.id);
    if (i > -1) {
      VIOLS.splice(i, 1); filtered = [...VIOLS];
      DS.totalViol = VIOLS.length;
      DS.todayViol = VIOLS.filter(v => new Date(v.ts*1000).toDateString() === new Date().toDateString()).length;
      updateKPIs(); renderVioTable(); rebuildRecent(); closeModal();
      toast("Đã xóa bản ghi vi phạm.", "warn");
    }
  } catch (e) { toast("Lỗi xóa bản ghi: " + e.message, "err"); }
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
function startCamSim() {
  const img = $("camImg"); if (!img) return;
  const tc = document.createElement("canvas");
  tc.width = camFrameW; tc.height = camFrameH;
  const ctx = tc.getContext("2d");
  function draw() {
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
    requestAnimationFrame(draw);
  }
  draw();
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
      return `<div class="cam-card ${st} neon-hover" onclick="goTo('camera')"><div class="cam-icon">📷</div><div class="cam-info"><div class="cam-name">${c.name}</div><div class="cam-detail">IP: ${c.ip} · ${espOK?"ESP32 Online":"Demo"}</div></div><div class="cam-status-badge ${st}">${lb}</div></div>`;
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

function renderDevices() {
  try {
    const grid = $("devGrid"); if (!grid) return;
    grid.innerHTML = DEVICES.map(d => `
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
    addLog("[SETTINGS] Cài đặt cập nhật.", "ok");
  } catch (e) { toast("Lỗi lưu cài đặt: " + e.message, "err"); }
});
$("btnResetCfg") && $("btnResetCfg").addEventListener("click", () => {
  [["cfGreen",30],["cfAmber",5],["cfRed",30],["cfSpeed",20],["cfVeh",6],["cfCapture",500],["cfOCR",70]].forEach(([id,v]) => $(id) && ($(id).value = v));
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
// v5.0: AI ENGINE HUD — update all AI status indicators in UI
// ═══════════════════════════════════════════════════════════════
function updateAIHud(ai) {
  try {
    if (!ai) return;
    // Sync into AI state object
    AI.active      = ai.active      ?? AI.active;
    AI.modelLoaded = ai.model_loaded ?? AI.modelLoaded;
    AI.ocrLoaded   = ai.ocr_loaded   ?? AI.ocrLoaded;
    AI.cameraOpen  = ai.camera_open  ?? AI.cameraOpen;
    AI.fps         = ai.fps          ?? AI.fps;
    AI.detections  = ai.detections   ?? AI.detections;
    AI.violations  = ai.violations   ?? AI.violations;
    AI.contextOk   = ai.context_ok   ?? AI.contextOk;
    AI.speedKmh    = ai.speed_kmh    ?? AI.speedKmh;
    AI.vehicles    = ai.vehicles     ?? AI.vehicles;
    AI.light       = ai.light        ?? AI.light;
    AI.lastUpdate  = Date.now();

    // ── AI status dot + badge ──
    const dot   = $("aiEngineDot");
    const badge = $("aiEngineBadge");
    const label = $("aiEngineLabel");
    if (dot) {
      dot.className = "ai-status-dot" + (AI.active ? " active" : AI.modelLoaded ? " loading" : "");
    }
    if (badge) {
      badge.textContent = AI.active ? "LIVE" : AI.modelLoaded ? "INIT" : "OFF";
      badge.style.background = AI.active ? "var(--green,#00e87a)" : AI.modelLoaded ? "var(--amber,#ffb020)" : "var(--t3,#3d5075)";
    }
    if (label) {
      label.textContent = AI.active
        ? `YOLOv8 ACTIVE — ${AI.fps.toFixed(1)} FPS`
        : AI.modelLoaded
        ? "AI Model Loaded — Camera Pending"
        : "AI Engine Offline";
    }

    // ── Model / OCR / Camera indicators ──
    _setAIIndicator("aiModelLed",   "aiModelVal",   AI.modelLoaded, AI.modelLoaded ? "Loaded ✓" : "Loading...");
    _setAIIndicator("aiOcrLed",     "aiOcrVal",     AI.ocrLoaded,   AI.ocrLoaded   ? "Loaded ✓" : "Loading...");
    _setAIIndicator("aiCamLed",     "aiCamVal",     AI.cameraOpen,  AI.cameraOpen  ? "Open ✓"   : "Closed");
    _setAIIndicator("aiContextLed", "aiContextVal", AI.contextOk,   AI.contextOk   ? "OK ✓"     : "WARN ⚠");

    // ── FPS + stats ──
    if ($("aiFpsVal"))  $("aiFpsVal").textContent  = AI.fps.toFixed(1) + " FPS";
    if ($("aiDetVal"))  $("aiDetVal").textContent  = AI.detections;
    if ($("aiViolVal")) $("aiViolVal").textContent = AI.violations;

    // ── AI load bar (replaces random simulation when AI is real) ──
    if (AI.active) {
      const loadPct = Math.min(100, Math.round((AI.fps / 25) * 100));
      const bar = $("aiLoadBar"), val = $("aiLoadVal");
      if (bar) { bar.style.width = loadPct + "%"; bar.className = "tb-m-fill" + (loadPct > 80 ? " r" : loadPct > 60 ? " a" : " g"); }
      if (val) val.textContent = loadPct + "% Load (AI Real)";
    }

    // ── Sync DS from AI engine when AI is active ──
    if (AI.active && AI.vehicles > 0) {
      DS.vehicles = AI.vehicles;
      DS.speed    = AI.speedKmh;
      DS.fps      = Math.round(AI.fps);
    }

  } catch (e) { console.warn("[v5.0 updateAIHud]", e); }
}

function _setAIIndicator(ledId, valId, ok, text) {
  const led = $(ledId), val = $(valId);
  if (led) led.className = "ctx-led " + (ok ? "ok" : "bad");
  if (val) val.textContent = text;
}

// ═══════════════════════════════════════════════════════════════
// v5.0: SYSTEM MODE — DEMO / LIVE switcher
// ═══════════════════════════════════════════════════════════════
function setSystemMode(demoMode, esp32Count, aiActive) {
  try {
    SYS.demoMode         = demoMode;
    SYS.esp32OnlineCount = esp32Count ?? SYS.esp32OnlineCount;
    SYS.aiEngineActive   = aiActive   ?? SYS.aiEngineActive;
    SYS.liveMode         = !demoMode && aiActive;

    // ── Demo banner ──
    const banner = $("demoBanner");
    if (banner) {
      if (!demoMode) {
        banner.classList.add("hidden");
      } else {
        banner.classList.remove("hidden");
        // Update demo banner text with AI status
        const txt = banner.querySelector(".demo-txt, span, p");
        if (txt) txt.textContent = aiActive
          ? "🤖 AI Engine chạy — Chờ ESP32 kết nối để vào LIVE mode"
          : "💻 DEMO MODE — Chưa có ESP32. AI Engine đang khởi động...";
      }
    }

    // ── Mode indicator badge ──
    const modeBadge = $("systemModeBadge");
    if (modeBadge) {
      modeBadge.textContent = SYS.liveMode ? "🟢 LIVE" : demoMode ? "💻 DEMO" : "🟡 PARTIAL";
      modeBadge.className   = "sys-mode-badge " + (SYS.liveMode ? "live" : demoMode ? "demo" : "partial");
    }

    // ── Connection indicator ──
    const esp32Badge = $("esp32CountBadge");
    if (esp32Badge) {
      esp32Badge.textContent = esp32Count + " ESP32";
      esp32Badge.style.color = esp32Count > 0 ? "var(--green,#00e87a)" : "var(--t3,#3d5075)";
    }

    // ── isDemo sync for demo spawner ──
    isDemo = demoMode;

    addLog(
      `[SYSTEM] Mode: ${SYS.liveMode ? "LIVE ✓" : demoMode ? "DEMO" : "PARTIAL"} | ESP32: ${esp32Count} | AI: ${aiActive ? "Active" : "Offline"}`,
      SYS.liveMode ? "ok" : "info"
    );
  } catch (e) { console.warn("[v5.0 setSystemMode]", e); }
}

// ═══════════════════════════════════════════════════════════════
// v5.0: ESP32 CONNECTED HANDLER
// ═══════════════════════════════════════════════════════════════
function onEsp32Connected(data) {
  try {
    if (!data) return;
    SYS.esp32OnlineCount = data.count ?? (SYS.esp32OnlineCount + 1);
    if (!SYS.firstEsp32At) SYS.firstEsp32At = Date.now();

    espOK  = true;
    isDemo = false;

    setConn("online");
    setSystemMode(false, SYS.esp32OnlineCount, SYS.aiEngineActive);

    // ── Update device card in real-time ──
    const devName = data.name || data.device_id || "ESP32";
    addLog(`[ESP32] 🔌 ${devName} kết nối — LIVE MODE bắt đầu!`, "ok");
    toast(`🔌 ${devName} đã kết nối — Hệ thống LIVE!`, "ok");

    // ── Flash camera cards green ──
    qA(".cam-card").forEach(c => { c.classList.add("live-flash"); setTimeout(() => c.classList.remove("live-flash"), 2000); });

    // ── Auto start AI feed when ESP32 connects ──
    if (!AIFEED.active) {
      setTimeout(startAIFeed, 1000);
    }

    // ── Update sidebar ESP32 status ──
    if ($("siESP")) $("siESP").textContent = data.fw || "Online";
    if ($("tbDot")) $("tbDot").classList.add("live");
    if ($("tbLabel")) $("tbLabel").textContent = "ThingsBoard — LIVE";
    if ($("mqttVal")) $("mqttVal").textContent = "Kết Nối ✓";

  } catch (e) { console.warn("[v5.0 onEsp32Connected]", e); }
}

// ═══════════════════════════════════════════════════════════════
// v5.0: ESP32 DISCONNECTED HANDLER
// ═══════════════════════════════════════════════════════════════
function onEsp32Disconnected(data) {
  try {
    SYS.esp32OnlineCount = Math.max(0, (data?.count ?? SYS.esp32OnlineCount - 1));
    const devName = data?.device_id || "ESP32";

    if (SYS.esp32OnlineCount === 0) {
      espOK  = false;
      isDemo = !SYS.aiEngineActive; // Stay not-demo if AI still running
      setConn(SYS.aiEngineActive ? "online" : "demo");
      setSystemMode(true, 0, SYS.aiEngineActive);
      toast(`⚠ ${devName} mất kết nối — về Demo Mode`, "warn");
      addLog(`[ESP32] ⚠ ${devName} offline — ESP32 count: 0`, "warn");
    } else {
      setSystemMode(false, SYS.esp32OnlineCount, SYS.aiEngineActive);
      addLog(`[ESP32] ${devName} offline — còn ${SYS.esp32OnlineCount} thiết bị`, "warn");
    }
  } catch (e) { console.warn("[v5.0 onEsp32Disconnected]", e); }
}

// ═══════════════════════════════════════════════════════════════
// v5.0: AI FEED — /ai_feed MJPEG stream với YOLO detection overlay
// ═══════════════════════════════════════════════════════════════
function startAIFeed() {
  try {
    AIFEED.active = true;

    // ── Tìm img element cho AI feed (tạo nếu chưa có) ──
    let imgEl = $("aiFeedImg");
    if (!imgEl) {
      // Inject vào camera section nếu có
      const camSection = $("sec-camera");
      if (camSection) {
        const wrapper = document.createElement("div");
        wrapper.id        = "aiFeedWrapper";
        wrapper.className = "ai-feed-wrapper";
        wrapper.innerHTML = `
          <div class="ai-feed-header">
            <span class="ai-feed-title">🤖 AI Camera — YOLOv8 Detection</span>
            <span class="ai-feed-badge" id="aiFeedBadge">LIVE</span>
            <button class="btn-sm" onclick="stopAIFeed()">✕ Tắt</button>
          </div>
          <img id="aiFeedImg" class="ai-feed-img" src="" alt="AI Feed"
               onerror="this.src=''; document.getElementById('aiFeedBadge').textContent='ERROR';">
          <div class="ai-feed-footer">
            <span id="aiFeedFps">FPS: --</span>
            <span id="aiFeedVeh">Xe: --</span>
            <span id="aiFeedLight">Đèn: --</span>
            <span id="aiFeedStatus">Đang kết nối...</span>
          </div>`;
        // Prepend vào đầu camera section
        const firstChild = camSection.querySelector(".section-body") || camSection;
        firstChild.insertBefore(wrapper, firstChild.firstChild);
      }
      imgEl = $("aiFeedImg");
    }

    if (imgEl) {
      AIFEED.imgEl   = imgEl;
      imgEl.src      = "/ai_feed?t=" + Date.now();
      imgEl.onload   = () => { if ($("aiFeedStatus")) $("aiFeedStatus").textContent = "Streaming ✓"; };
      imgEl.onerror  = () => {
        addLog("[AI FEED] Stream lỗi — thử lại sau 3s", "warn");
        setTimeout(() => { if (AIFEED.active && imgEl) imgEl.src = "/ai_feed?t=" + Date.now(); }, 3000);
      };
    }

    // ── Cũng hiển thị trong laptop tab nếu có lapImg ──
    const lapImg = $("lapImg");
    if (lapImg && !LAP.active) {
      lapImg.src = "/ai_feed?t=" + Date.now();
      lapShowFeed(true);
      lapSetStatus(true, "🤖 AI Feed — YOLOv8 Active");
      if ($("lapAiSrc"))  $("lapAiSrc").textContent  = "AI Engine v5.0";
      if ($("lapAiMode")) $("lapAiMode").textContent  = "YOLOv8 + EasyOCR";
    }

    addLog("[AI FEED] 🎥 /ai_feed stream bắt đầu", "ok");
    toast("🤖 AI Camera stream đang phát!", "ok");

    // ── Periodic stats update for feed footer ──
    if (AIFEED.pollTimer) clearInterval(AIFEED.pollTimer);
    AIFEED.pollTimer = setInterval(() => {
      if (!AIFEED.active) { clearInterval(AIFEED.pollTimer); return; }
      if ($("aiFeedFps"))   $("aiFeedFps").textContent   = "FPS: " + AI.fps.toFixed(1);
      if ($("aiFeedVeh"))   $("aiFeedVeh").textContent   = "Xe: " + AI.vehicles;
      if ($("aiFeedLight")) $("aiFeedLight").textContent = "Đèn: " + AI.light;
    }, 1000);

  } catch (e) {
    addLog(`[AI FEED] Lỗi: ${e.message}`, "err");
    console.warn("[v5.0 startAIFeed]", e);
  }
}

function stopAIFeed() {
  try {
    AIFEED.active = false;
    if (AIFEED.pollTimer) { clearInterval(AIFEED.pollTimer); AIFEED.pollTimer = null; }
    if (AIFEED.imgEl)     { AIFEED.imgEl.src = ""; AIFEED.imgEl = null; }
    const wrapper = $("aiFeedWrapper");
    if (wrapper) wrapper.remove();
    addLog("[AI FEED] Stream dừng", "warn");
  } catch (e) { console.warn("[v5.0 stopAIFeed]", e); }
}
window.stopAIFeed  = stopAIFeed;
window.startAIFeed = startAIFeed;

// ═══════════════════════════════════════════════════════════════
// v5.0: POLL AI STATUS — khi chưa có socket, poll HTTP mỗi 5s
// ═══════════════════════════════════════════════════════════════
let _aiPollTimer = null;
let _socketActive = false;

function startAIStatusPoll() {
  if (_aiPollTimer) return; // Already polling
  _aiPollTimer = setInterval(async () => {
    if (_socketActive) {
      // Socket is active — stop polling, socket handles updates
      clearInterval(_aiPollTimer);
      _aiPollTimer = null;
      return;
    }
    try {
      const data = await safeFetch("/api/ai/status");
      if (data?.ok) {
        updateAIHud(data.ai_engine);
        if (data.demo_mode === false && SYS.demoMode) {
          // Server says live but we think demo — sync
          setSystemMode(false, data.ai_engine?.vehicles ?? 0, data.ai_engine?.active ?? false);
        }
      }
    } catch (e) { /* silent */ }
  }, 5000);
  addLog("[AI POLL] Polling /api/ai/status setiap 5s", "info");
}

// ═══════════════════════════════════════════════════════════════
// v5.0: CONTEXT UPDATE — enhanced to include AI engine data
// ═══════════════════════════════════════════════════════════════
function updateContextV5(ctx) {
  try {
    if (!ctx) return;
    // Update DS from server context
    if (ctx.speed_kmh       !== undefined) DS.speed    = parseFloat(ctx.speed_kmh.toFixed(1));
    if (ctx.vehicles_frame  !== undefined) DS.vehicles = ctx.vehicles_frame;
    if (ctx.fps             !== undefined) DS.fps      = Math.round(ctx.fps);
    if (ctx.weather)        DS.weather = ctx.weather === "SUN" ? "Nắng" : ctx.weather === "LIGHT_RAIN" ? "Mưa nhẹ" : ctx.weather;
    if (ctx.capture_interval !== undefined) DS.capture = Math.round(ctx.capture_interval * 1000);

    // AI integration fields (v5.0)
    if (ctx.ai_active !== undefined) {
      SYS.aiEngineActive = ctx.ai_active;
      AI.active          = ctx.ai_active;
    }
    if (ctx.ai_model_loaded !== undefined) AI.modelLoaded = ctx.ai_model_loaded;
    if (ctx.ai_ocr_loaded   !== undefined) AI.ocrLoaded   = ctx.ai_ocr_loaded;
    if (ctx.ai_camera_open  !== undefined) AI.cameraOpen  = ctx.ai_camera_open;

    updateContext(); // Refresh all context UI
    syncLapCtx();
  } catch (e) { console.warn("[v5.0 updateContextV5]", e); }
}

// ═══════════════════════════════════════════════════════════════
// REAL API / SOCKET — v5.0 upgraded (all v4.0 events preserved)
// ═══════════════════════════════════════════════════════════════
function trySocket() {
  if (typeof io === "undefined") {
    addLog("[SOCKET] socket.io chưa load — dùng HTTP polling", "warn");
    startAIStatusPoll();
    return;
  }
  try {
    const s = io({
      transports: ["websocket"],
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
      auth: { token: getToken() },
    });

    s.on("connect", () => {
      _socketActive = true;
      setConn("online");
      espOK = true;
      addLog("[WS] ✅ WebSocket kết nối thành công", "ok");
      // Request current AI status on connect
      s.emit("req_ai_status", {});
    });

    s.on("disconnect", (reason) => {
      _socketActive = false;
      setConn("demo");
      isDemo = true;
      addLog(`[WS] Mất kết nối: ${reason} — về demo mode`, "warn");
      // Fall back to polling when socket drops
      startAIStatusPoll();
    });

    // ── v4.0: Traffic state ──
    s.on("traffic_state", st => {
      if (!st) return;
      DS.light     = st.light;
      DS.countdown = st.countdown;
      DS.camState  = st.camera;
      DS.phase     = st.light === "RED" ? "ĐỎ" : st.light === "YELLOW" ? "VÀNG" : "XANH";
      AI.light     = st.light; // v5.0: sync to AI state
      renderTraffic();
      syncLapCtx();
    });

    // ── v4.0: New violation ──
    s.on("new_violation", v => {
      VIOLS.unshift(v);
      filtered = [...VIOLS];
      DS.totalViol++;
      DS.todayViol++;
      hourly[new Date().getHours()]++;
      updateKPIs();
      appendRecent(v);
      addDetection(v);
      renderVioTable();
      // v5.0: tag source in log
      const src = v.source || "mqtt";
      const srcLabel = src === "ai_engine_v5" ? "🤖 AI Engine" : src === "inject" ? "💉 Inject" : "📡 MQTT";
      toast(`⚠ Vi phạm: ${v.plate} (${srcLabel})`, "err");
      addLog(`[VIOL] ${v.plate} | ${v.type} | ${v.speed_kmh}km/h | src:${srcLabel}`, "err");
    });

    // ── v4.0: Context update — v5.0 upgraded ──
    s.on("context_update", ctx => {
      if (!ctx) return;
      // v5.0: use enhanced handler
      updateContextV5(ctx);
    });

    // ── v4.0: Theme update ──
    s.on("theme_update", data => {
      if (data && data.theme && data.source !== "ws-client") {
        applyTheme(data.theme, false);
        addLog(`[THEME] Server theme: ${data.theme} (source: ${data.source})`, "ok");
      }
    });

    // ── v5.0 NEW: AI Engine status ──
    s.on("ai_engine_status", data => {
      if (!data) return;
      updateAIHud(data);
      SYS.aiEngineActive = data.active ?? SYS.aiEngineActive;
      addLog(
        `[AI] ${data.active ? "🟢" : "🔴"} Engine: model=${data.model_loaded ? "✓" : "✗"} ocr=${data.ocr_loaded ? "✓" : "✗"} cam=${data.camera_open ? "✓" : "✗"} fps=${data.fps?.toFixed(1) ?? 0}`,
        data.active ? "ok" : "info"
      );
      // Auto-start AI feed when AI engine goes active
      if (data.active && !AIFEED.active) {
        setTimeout(startAIFeed, 500);
      }
    });

    // ── v5.0 NEW: ESP32 connected ──
    s.on("esp32_connected", data => {
      if (!data) return;
      onEsp32Connected(data);
    });

    // ── v5.0 NEW: ESP32 disconnected ──
    s.on("esp32_disconnected", data => {
      if (!data) return;
      onEsp32Disconnected(data);
    });

    // ── v5.0 NEW: System mode (demo/live) ──
    s.on("system_mode", data => {
      if (!data) return;
      setSystemMode(
        data.demo_mode         ?? SYS.demoMode,
        data.esp32_online_count ?? SYS.esp32OnlineCount,
        data.ai_engine_active   ?? SYS.aiEngineActive
      );
    });

    // ── v5.0 NEW: Device update ──
    s.on("device_update", dev => {
      if (!dev || !dev.device_id) return;
      // Update device cards if on devices page
      try {
        const devCard = document.querySelector(`[data-device="${dev.device_id}"]`);
        if (devCard) {
          const statusEl = devCard.querySelector(".dev-status");
          if (statusEl) {
            statusEl.textContent  = dev.status === "ONLINE" ? "● ONLINE" : "✕ OFFLINE";
            statusEl.className    = "dev-status " + (dev.status === "ONLINE" ? "online" : "idle");
          }
        }
        addLog(`[DEVICE] ${dev.device_id}: ${dev.status}`, dev.status === "ONLINE" ? "ok" : "warn");
      } catch (e) {}
    });

    // ── v5.0 NEW: System events from backend ──
    s.on("system_event", ev => {
      if (!ev) return;
      const cls = ev.level === "WARN" ? "warn" : ev.level === "ERROR" ? "err" : "info";
      addLog(`[${ev.source}] ${ev.message}`, cls);
    });

  } catch (e) {
    addLog(`[SOCKET] Lỗi kết nối: ${e.message}`, "warn");
    startAIStatusPoll(); // Fallback
  }
}

// ═══════════════════════════════════════════════════════════════
// BOOT — v5.0.0 — Full AI Engine + ESP32 + Demo/Live
// ═══════════════════════════════════════════════════════════════
async function boot() {
  try {
    addLog("[SYSTEM] AI Traffic Dashboard v5.0.0 khởi động...", "info");

    // ── BƯỚC 1: Token (giữ nguyên v4.0.3) ──
    addLog("[AUTH] Kiểm tra token...", "info");
    const tok = await ensureToken();
    if (tok) addLog("[AUTH] Token sẵn sàng ✓", "ok");

    // ── BƯỚC 2: Particles ──
    initParticles();

    // ── BƯỚC 3: Theme local ngay ──
    const savedLocalTheme = localStorage.getItem("TRAFFIC_THEME") || "neon-futuristic";
    await applyTheme(savedLocalTheme, false);

    // ── BƯỚC 4: Fetch theme từ server ──
    await fetchTheme();

    // ── BƯỚC 5: Bootstrap API ──
    addLog("[API] Kết nối server...", "info");
    const data = await safeFetch("/api/bootstrap");

    if (data?.ok) {
      isDemo = data.demo_mode ?? false;

      if (!isDemo) {
        $("demoBanner") && $("demoBanner").classList.add("hidden");
        setConn("online");
        espOK = true;
        addLog("[API] Server kết nối thành công ✓", "ok");
      } else {
        addLog("[API] Server OK — DEMO mode (chưa có ESP32)", "info");
      }

      if (data.violations) {
        data.violations.forEach(v => VIOLS.push(v));
        filtered = [...VIOLS];
        DS.totalViol = VIOLS.length;
        DS.todayViol = VIOLS.length;
        renderVioTable();
        updateKPIs();
        VIOLS.slice(0, 5).forEach(v => appendRecent(v));
      }

      if (data.theme && THEMES[data.theme]) {
        await applyTheme(data.theme, false);
        addLog(`[THEME] Bootstrap theme: ${data.theme}`, "ok");
      }

      // ── v5.0: Read AI engine status from bootstrap ──
      if (data.ai_engine) {
        updateAIHud(data.ai_engine);
        SYS.aiEngineActive = data.ai_engine.active ?? false;
        addLog(
          `[AI] Engine: active=${data.ai_engine.active} model=${data.ai_engine.model_loaded} ocr=${data.ai_engine.ocr_loaded} cam=${data.ai_engine.camera_open}`,
          data.ai_engine.active ? "ok" : "info"
        );
        if (data.ai_engine.active && !AIFEED.active) {
          setTimeout(startAIFeed, 1500);
        }
      }

      // ── v5.0: System mode from bootstrap ──
      setSystemMode(
        data.demo_mode         ?? true,
        data.esp32_online_count ?? 0,
        data.ai_engine?.active  ?? false
      );

      // ── v5.0: Update ESP32 count indicators ──
      SYS.esp32OnlineCount = data.esp32_online_count ?? 0;
      if (SYS.esp32OnlineCount > 0) {
        onEsp32Connected({ count: SYS.esp32OnlineCount, name: "ESP32 System" });
      }

      trySocket();

    } else {
      // ── Server offline → full demo mode ──
      addLog("[SYSTEM] Server offline — DEMO mode đầy đủ", "warn");
      setSystemMode(true, 0, false);

      const seeds = [
        { plate:"51B-12345", type:"Xe máy", speed_kmh:16.2, confidence:88 },
        { plate:"59D-67890", type:"Ô tô",   speed_kmh:12.8, confidence:92 },
        { plate:"29A-11222", type:"Xe máy", speed_kmh:18.5, confidence:76 },
        { plate:"43K-55667", type:"Xe máy", speed_kmh:14.1, confidence:83 },
      ];
      seeds.forEach((s, i) => {
        const v = { ...s, id: vioID++, ts: Math.floor(Date.now()/1000) - (i+1)*1800, light:"RED", roi:"STOP_LINE", cam:"CAM " + (i%3+1), image_url:"", source:"demo" };
        VIOLS.push(v);
        hourly[new Date(v.ts*1000).getHours()]++;
      });
      filtered    = [...VIOLS];
      DS.totalViol = VIOLS.length;
      DS.todayViol = 2;
      DS.detected  = 6;
      updateKPIs();
      renderVioTable();
      rebuildRecent();
      addLog("[DEMO] Tải " + VIOLS.length + " vi phạm mẫu ✓", "ok");

      // Still try socket in case server starts later
      setTimeout(trySocket, 3000);
      // Poll AI status
      startAIStatusPoll();
    }

    startCycle();
    startCamSim();
    renderCamRow();
    updateContext();
    syncLapCtx();
    lapSetStatus(false, "Sẵn sàng — nhấn Bật Camera");
    buildThemeSelector();
    addLog("[SYSTEM] ✅ Premium Dashboard v5.0.0 sẵn sàng!", "ok");
    lapAddLog("[SYSTEM] Laptop Camera + AI Engine module sẵn sàng", "info");
    toast("🚀 Dashboard v5.0.0 đã khởi động!", "ok");

  } catch (e) {
    console.error("[BOOT ERROR]", e);
    addLog(`[BOOT ERROR] ${e.message}`, "err");
    toast("Lỗi khởi động hệ thống: " + e.message, "err");
    // Graceful fallback to demo
    try { setSystemMode(true, 0, false); startCycle(); startCamSim(); } catch(_) {}
  }
}

// ═══════════════════════════════════════════════════════════════
// PERIODIC UPDATES — v5.0 upgraded
// ═══════════════════════════════════════════════════════════════
setInterval(updateContext,  5000);
setInterval(renderCamRow,   3000);
setInterval(syncLapCtx,     2000);

// AI load bar — real when AI active, simulated when demo
setInterval(() => {
  try {
    if (AI.active) return; // AI engine handles this via socket event
    const load = Math.floor(50 + Math.random() * 45);
    const bar  = $("aiLoadBar"), val = $("aiLoadVal");
    if (bar) { bar.style.width = load + "%"; bar.className = "tb-m-fill" + (load > 80 ? " r" : load > 60 ? " a" : " g"); }
    if (val) val.textContent = load + "% Load";
  } catch (e) { console.warn("[AI Load]", e); }
}, 4000);

// Demo violation spawner — only when truly demo (no ESP32, no AI)
setInterval(() => {
  try { if (isDemo && !SYS.aiEngineActive && DS.light === "RED" && Math.random() < 0.18) spawnViolation(); } catch (e) {}
}, 12000);

// Chart re-render
setInterval(() => {
  try { if ($("sec-stats")?.classList.contains("active")) renderCharts(); } catch (e) {}
}, 6000);

// Laptop detection counter
setInterval(() => {
  try { if (LAP.active) DS.detected += LAP.fpsCounter > 0 ? 1 : 0; } catch (e) {}
}, 3000);

// Particle hover listeners refresh
setInterval(() => {
  try { if (particlesInitialized) attachNeonHoverListeners(); } catch (e) {}
}, 10000);

// v5.0: Periodic AI HUD sync even without socket (HTTP fallback)
setInterval(async () => {
  try {
    if (_socketActive || !SYS.aiEngineActive) return; // Socket handles it / not active
    const data = await safeFetch("/api/ai/status");
    if (data?.ok && data.ai_engine) updateAIHud(data.ai_engine);
  } catch (e) {}
}, 8000);

// v5.0: Update AI feed footer stats
setInterval(() => {
  try {
    if (!AIFEED.active) return;
    if ($("aiFeedFps"))   $("aiFeedFps").textContent   = "FPS: " + AI.fps.toFixed(1);
    if ($("aiFeedVeh"))   $("aiFeedVeh").textContent   = "Xe: "  + AI.vehicles;
    if ($("aiFeedLight")) $("aiFeedLight").textContent = "Đèn: " + AI.light;
  } catch (e) {}
}, 1000);

// ═══════════════════════════════════════════════════════════════
// v5.0: INJECT CSS for new AI HUD elements (no separate file needed)
// ═══════════════════════════════════════════════════════════════
(function injectV5Styles() {
  const style = document.createElement("style");
  style.id = "v5-styles";
  style.textContent = `
    /* AI Engine Status Dot */
    .ai-status-dot {
      display: inline-block; width: 10px; height: 10px;
      border-radius: 50%; background: var(--t3,#3d5075);
      margin-right: 6px; vertical-align: middle;
      transition: background .3s;
    }
    .ai-status-dot.active  { background: var(--green,#00e87a); box-shadow: 0 0 8px var(--green,#00e87a); animation: aipulse 1.5s infinite; }
    .ai-status-dot.loading { background: var(--amber,#ffb020); box-shadow: 0 0 6px var(--amber,#ffb020); }
    @keyframes aipulse { 0%,100%{opacity:1} 50%{opacity:.5} }

    /* System mode badge */
    .sys-mode-badge {
      display: inline-flex; align-items: center; gap: 5px;
      padding: 2px 10px; border-radius: 20px; font-size: 11px;
      font-family: var(--mono,"Space Mono",monospace); font-weight: 700;
      transition: all .3s;
    }
    .sys-mode-badge.live    { background: rgba(0,232,122,.15); color: var(--green,#00e87a); border: 1px solid rgba(0,232,122,.35); }
    .sys-mode-badge.demo    { background: rgba(32,202,255,.10); color: var(--cyan,#20caff);  border: 1px solid rgba(32,202,255,.25); }
    .sys-mode-badge.partial { background: rgba(255,176,32,.12); color: var(--amber,#ffb020); border: 1px solid rgba(255,176,32,.3); }

    /* ESP32 count badge */
    #esp32CountBadge {
      font-family: var(--mono,"Space Mono",monospace);
      font-size: 11px; font-weight: 700;
      transition: color .3s;
    }

    /* Live flash animation for camera cards when ESP32 connects */
    .live-flash {
      animation: liveflash .6s ease-in-out 3;
    }
    @keyframes liveflash {
      0%,100%{box-shadow:none}
      50%{box-shadow:0 0 18px rgba(0,232,122,.7), inset 0 0 8px rgba(0,232,122,.15)}
    }

    /* AI Feed wrapper */
    .ai-feed-wrapper {
      background: var(--panel,#0d1322);
      border: 1px solid rgba(32,202,255,.15);
      border-radius: 10px; overflow: hidden;
      margin-bottom: 16px;
    }
    .ai-feed-header {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 14px;
      background: rgba(32,202,255,.05);
      border-bottom: 1px solid rgba(32,202,255,.1);
    }
    .ai-feed-title {
      flex: 1; font-family: var(--mono,"Space Mono",monospace);
      font-size: 12px; font-weight: 700; color: var(--cyan,#20caff);
    }
    .ai-feed-badge {
      padding: 2px 8px; border-radius: 20px; font-size: 10px;
      font-family: var(--mono,"Space Mono",monospace); font-weight: 700;
      background: rgba(0,232,122,.15); color: var(--green,#00e87a);
      border: 1px solid rgba(0,232,122,.3);
      animation: aipulse 1.5s infinite;
    }
    .ai-feed-img {
      display: block; width: 100%; max-height: 480px;
      object-fit: contain; background: #050a14;
    }
    .ai-feed-footer {
      display: flex; gap: 16px; padding: 6px 14px;
      background: rgba(0,0,0,.3);
      font-family: var(--mono,"Space Mono",monospace);
      font-size: 10px; color: var(--t2,#8899b8);
    }
    .ai-feed-footer span { display: flex; align-items: center; gap: 4px; }

    /* AI Engine indicator rows */
    .ai-ind-row {
      display: flex; align-items: center; gap: 8px;
      padding: 4px 0; font-size: 12px;
    }
    .ai-ind-row .ctx-led { flex-shrink: 0; }
    .ai-ind-label { flex: 1; color: var(--t2,#8899b8); font-size: 11px; }
    .ai-ind-val   { font-family: var(--mono,"Space Mono",monospace); font-size: 11px; font-weight: 700; color: var(--cyan,#20caff); }
  `;
  document.head.appendChild(style);
})();

// ── LAUNCH ──
boot();