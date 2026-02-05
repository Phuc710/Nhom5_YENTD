// main.js
(function () {
  "use strict";

  const TOKEN_KEY = "TRAFFIC_AI_TOKEN";
  const $ = (s) => document.querySelector(s);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function getToken() {
    // ✅ chịu được cache cũ: nếu còn "token" thì vẫn vào được
    return localStorage.getItem(TOKEN_KEY) || localStorage.getItem("token");
  }
  function clearToken() {
    // ✅ dọn cả 2 key cho sạch
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("token");
  }
  function goLogin() {
    window.location.replace("/");
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function toLightClass(v) {
    const s = String(v || "").toUpperCase();
    if (s === "RED") return "red";
    if (s === "GREEN") return "green";
    if (s === "YELLOW") return "yellow";
    return "";
  }

  function normalizeViolation(v) {
    return {
      id: v?.id || String(Date.now() + Math.random()),
      img: v?.img || "/static/imge/admin.jpg",
      plate: v?.plate || "N/A",
      type: v?.type || "N/A",
      speed: v?.speed || "N/A",
      light: v?.light || "N/A",
      roi: v?.roi || "Vạch dừng (ROI)",
      time: v?.time || new Date().toLocaleString(),
      note: v?.note || "",
      raw: v
    };
  }

  async function apiBootstrap(token) {
    const r = await fetch("/api/bootstrap", {
      headers: { Authorization: "Bearer " + token },
    });
    if (r.status === 401) throw new Error("unauthorized");
    const data = await r.json();
    if (!data.ok) throw new Error("bootstrap failed");
    return data;
  }

  // ===== STATE =====
  let token = null;
  let traffic = { light: "RED", countdown: 30 };
  const violations = [];

  // ===== SSE =====
  let es = null;

  function stopSSE() {
    try { es?.close(); } catch {}
    es = null;
  }

  function startSSE() {
    try {
      es = new EventSource(`/api/events?token=${encodeURIComponent(token)}`);
    } catch {
      return;
    }

    es.addEventListener("violation", (e) => {
      try {
        violations.unshift(normalizeViolation(JSON.parse(e.data)));
        renderViolations();
      } catch {}
    });

    es.addEventListener("iot_state", (e) => {
      try {
        traffic = Object.assign(traffic, JSON.parse(e.data));
        renderTop();
      } catch {}
    });

    // ✅ nếu server dùng generic message: {"type":"violation"/"iot_state"}
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data || "{}");
        if (data.type === "violation") {
          violations.unshift(normalizeViolation(data.payload || data));
          renderViolations();
        }
        if (data.type === "iot_state") {
          traffic = Object.assign(traffic, data.payload || data);
          renderTop();
        }
      } catch {}
    };
  }

  // ===== UI =====
  const vTableBody = $("#vTableBody");
  const lightText = $("#lightText");
  const countdownEl = $("#countdown");

  function renderTop() {
    if (lightText) lightText.textContent = traffic.light;
    if (countdownEl) countdownEl.textContent = traffic.countdown;
  }

  function renderViolations() {
    if (!vTableBody) return;
    if (!violations.length) {
      vTableBody.innerHTML = `<tr><td colspan="8">Chưa có dữ liệu</td></tr>`;
      return;
    }
    vTableBody.innerHTML = violations.map(v => `
      <tr>
        <td><img src="${escapeHtml(v.img)}" class="tThumb"></td>
        <td>${escapeHtml(v.plate)}</td>
        <td>${escapeHtml(v.type)}</td>
        <td>${escapeHtml(v.speed)}</td>
        <td><span class="${toLightClass(v.light)}">${escapeHtml(v.light)}</span></td>
        <td>${escapeHtml(v.roi)}</td>
        <td>${escapeHtml(v.time)}</td>
        <td>${escapeHtml(v.note)}</td>
      </tr>
    `).join("");
  }

  // ===== INIT =====
  async function init() {
    token = getToken();

    // ✅ tự đồng bộ: nếu đang có "token" cũ → chuyển sang TRAFFIC_AI_TOKEN
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.removeItem("token");
    }

    if (!token) return goLogin();

    try {
      const boot = await apiBootstrap(token);
      traffic = boot.traffic || traffic;

      (boot.violations || []).forEach(v =>
        violations.push(normalizeViolation(v))
      );

      renderTop();
      renderViolations();
      startSSE();

      window.__TRAFFIC_WEB__ = {
        status: () => ({ token, traffic, sse: !!es }),
        stopSSE,
        startSSE,
        logout: () => { stopSSE(); clearToken(); goLogin(); }
      };

    } catch (e) {
      console.error(e);
      stopSSE();
      clearToken();
      goLogin();
    }
  }

  init();
})();
