"use strict";

const TOKEN_KEY = "TRAFFIC_AI_TOKEN";
const API_BASE = "";

const SECTION_META = {
  overview: {
    title: "T\u1ed5ng quan h\u1ec7 th\u1ed1ng",
    subtitle: "Theo d\u00f5i tr\u1ea1ng th\u00e1i camera, heartbeat thi\u1ebft b\u1ecb v\u00e0 vi ph\u1ea1m giao th\u00f4ng theo th\u1eddi gian th\u1ef1c."
  },
  cameras: {
    title: "Danh s\u00e1ch camera",
    subtitle: "Tra c\u1ee9u camera, t\u00ecm theo v\u1ecb tr\u00ed v\u00e0 theo d\u00f5i tr\u1ea1ng th\u00e1i online ho\u1eb7c offline th\u1ef1c t\u1ebf."
  },
  livestream: {
    title: "Livestream camera",
    subtitle: "Xem lu\u1ed3ng camera qua backend proxy c\u00f9ng th\u00f4ng tin tr\u1ea1ng th\u00e1i v\u00e0 vi ph\u1ea1m g\u1ea7n nh\u1ea5t."
  },
  violations: {
    title: "Danh s\u00e1ch vi ph\u1ea1m",
    subtitle: "Tra c\u1ee9u vi ph\u1ea1m theo bi\u1ec3n s\u1ed1, camera, tr\u1ea1ng th\u00e1i v\u00e0 th\u1eddi gian t\u1eeb database th\u1eadt."
  },
  manage: {
    title: "Qu\u1ea3n l\u00fd camera",
    subtitle: "Th\u00eam, s\u1eeda, x\u00f3a camera qua API th\u1eadt v\u00e0 c\u1eadp nh\u1eadt danh s\u00e1ch ngay trong dashboard."
  },
  settings: {
    title: "C\u00e0i \u0111\u1eb7t h\u1ec7 th\u1ed1ng",
    subtitle: "T\u1ed5ng h\u1ee3p c\u00e1c endpoint v\u1eadn h\u00e0nh v\u00e0 ghi ch\u00fa runtime c\u1ee7a h\u1ec7 th\u1ed1ng production hi\u1ec7n t\u1ea1i."
  }
};

const state = {
  cameras: [],
  violations: [],
  totalViolations: 0,
  page: 1,
  limit: 20,
  selectedLiveCameraId: "",
  editingCameraId: "",
  activeSection: "overview",
  sse: null,
  sseRetryMs: 2000,
  backendOnline: false,
  realtimeConnected: false,
  eventFeed: []
};

let toastTimer = null;

function $(id) {
  return document.getElementById(id);
}

function token() {
  return (localStorage.getItem(TOKEN_KEY) || "").trim();
}

function ensureAuth() {
  if (!token()) {
    window.location.replace("/login");
    return false;
  }
  return true;
}

async function apiFetch(path, options = {}) {
  const t = token();
  if (!t) return null;

  const headers = {
    Authorization: `Bearer ${t}`,
    ...(options.headers || {})
  };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.replace("/login");
    return null;
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${path} ${text.slice(0, 120)}`);
  }
  return res.json().catch(() => null);
}

function showToast(msg) {
  const node = $("toast");
  if (!node) return;
  node.textContent = msg;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 1800);
}

function setManageFeedback(message, type = "info") {
  const node = $("manageFormFeedback");
  if (!node) return;
  if (!message) {
    node.textContent = "";
    node.className = "manage-feedback hidden";
    return;
  }
  node.textContent = message;
  node.className = `manage-feedback manage-feedback--${type}`;
}

function syncManageFormState() {
  const isEditing = Boolean(state.editingCameraId);
  const title = $("manageFormTitle");
  const mode = $("manageFormMode");
  const saveButton = $("btnSaveCamera");

  if (title) {
    title.textContent = isEditing ? "Cập nhật camera" : "Thêm mới camera";
  }
  if (mode) {
    mode.textContent = isEditing ? "Edit" : "Create";
    mode.className = isEditing ? "badge badge-online" : "badge badge-muted";
  }
  if (saveButton) {
    saveButton.textContent = isEditing ? "Lưu cập nhật" : "Thêm camera";
  }
}

function fmtDate(value) {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("vi-VN");
}

function cameraStatus(camera) {
  const raw = String(camera?.status || camera?.device_status || "OFFLINE").toUpperCase();
  return raw === "ONLINE" ? "ONLINE" : "OFFLINE";
}

function badgeStatus(status) {
  return `<span class="badge ${status === "ONLINE" ? "badge-online" : "badge-offline"}">${status}</span>`;
}

function violationStatusBadge(status) {
  const value = String(status || "NEW").toUpperCase();
  const positive = value === "CONFIRMED" || value === "CLOSED";
  return `<span class="badge ${positive ? "badge-online" : "badge-offline"}">${value}</span>`;
}

function pushEventFeed(title, meta) {
  state.eventFeed.unshift({ title, meta, ts: new Date().toISOString() });
  state.eventFeed = state.eventFeed.slice(0, 6);
  renderOverview();
}

function setSection(name) {
  state.activeSection = name;

  document.querySelectorAll(".nav-item").forEach((node) => {
    node.classList.toggle("active", node.dataset.section === name);
  });

  document.querySelectorAll(".content-section").forEach((node) => {
    node.classList.toggle("active", node.id === `section-${name}`);
  });

  const meta = SECTION_META[name] || SECTION_META.overview;
  $("pageTitle").textContent = meta.title;
  $("pageSubtitle").textContent = meta.subtitle;
}

function attachSidebarNavigation() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => setSection(btn.dataset.section));
  });
}

function renderOverview() {
  const totalCameras = state.cameras.length;
  const onlineCameras = state.cameras.filter((camera) => cameraStatus(camera) === "ONLINE").length;
  const visibleViolations = state.violations.length;

  $("statTotalCameras").textContent = String(totalCameras);
  $("statOnlineCameras").textContent = String(onlineCameras);
  $("statVisibleViolations").textContent = String(visibleViolations);
  $("statRealtimeState").textContent = state.realtimeConnected ? "LIVE" : "WAIT";

  $("overviewBackend").textContent = state.backendOnline ? "Online" : "Offline";
  $("overviewRealtime").textContent = state.realtimeConnected ? "Connected" : "Disconnected";
  $("overviewOnlineRatio").textContent = `${onlineCameras} / ${totalCameras}`;
  $("overviewViolations").textContent = `${state.totalViolations}`;

  const feed = $("eventFeed");
  if (!feed) return;

  if (!state.eventFeed.length) {
    feed.innerHTML = `<div class="event-item"><strong>Ch\u01b0a c\u00f3 s\u1ef1 ki\u1ec7n m\u1edbi</strong><div class="event-item__meta">S\u1ef1 ki\u1ec7n realtime s\u1ebd xu\u1ea5t hi\u1ec7n t\u1ea1i \u0111\u00e2y khi camera \u0111\u1ed5i tr\u1ea1ng th\u00e1i ho\u1eb7c c\u00f3 vi ph\u1ea1m m\u1edbi.</div></div>`;
    return;
  }

  feed.innerHTML = state.eventFeed.map((item) => `
    <div class="event-item">
      <strong>${item.title}</strong>
      <div class="event-item__meta">${item.meta}</div>
      <div class="event-item__meta">${fmtDate(item.ts)}</div>
    </div>
  `).join("");
}

function renderCameras() {
  const grid = $("cameraCardGrid");
  const empty = $("cameraEmptyState");
  if (!grid || !empty) return;

  const q = ($("cameraSearch")?.value || "").trim().toLowerCase();
  const sf = ($("cameraStatusFilter")?.value || "ALL").toUpperCase();
  const total = state.cameras.length;
  const online = state.cameras.filter((cam) => cameraStatus(cam) === "ONLINE").length;
  const offline = Math.max(0, total - online);
  const rows = state.cameras.filter((cam) => {
    const st = cameraStatus(cam);
    if (sf !== "ALL" && st !== sf) return false;
    if (!q) return true;
    const hay = [cam.camera_name, cam.camera_code, cam.location_name].join(" ").toLowerCase();
    return hay.includes(q);
  });

  $("cameraCountTotal").textContent = String(total);
  $("cameraCountOnline").textContent = String(online);
  $("cameraCountOffline").textContent = String(offline);

  if (!rows.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    renderOverview();
    return;
  }

  empty.classList.add("hidden");
  grid.innerHTML = rows.map((cam) => {
    const st = cameraStatus(cam);
    return `
      <article class="camera-card">
        <div class="camera-card__head">
          <div class="camera-card__title">
            <strong>${cam.camera_name || "--"}</strong>
            <span class="camera-card__code">${cam.camera_code || "--"}</span>
          </div>
          ${badgeStatus(st)}
        </div>
        <div class="camera-card__body">
          <div class="camera-card__row">
            <span class="camera-card__label">\u0110\u1ecba \u0111i\u1ec3m</span>
            <span class="camera-card__value camera-card__value--location">${cam.location_name || "--"}</span>
          </div>
          <div class="camera-card__row">
            <span class="camera-card__label">C\u1eadp nh\u1eadt cu\u1ed1i</span>
            <span class="camera-card__value">${fmtDate(cam.last_seen || cam.last_seen_at)}</span>
          </div>
          <div class="camera-card__row">
            <span class="camera-card__label">Stream</span>
            <span class="camera-card__value">${cam.stream_url ? "S\u1eb5n s\u00e0ng" : "Ch\u01b0a c\u1ea5u h\u00ecnh"}</span>
          </div>
        </div>
        <div class="camera-card__footer">
          <button class="link-btn" data-live="${cam.camera_code}">Livestream</button>
          <button class="link-btn" data-edit="${cam.camera_code}">Ch\u1ec9nh s\u1eeda</button>
        </div>
      </article>
    `;
  }).join("");

  grid.querySelectorAll("button[data-live]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedLiveCameraId = btn.dataset.live;
      $("liveCameraSelect").value = state.selectedLiveCameraId;
      renderLiveCamera();
      setSection("livestream");
    });
  });

  grid.querySelectorAll("button[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      beginEditCamera(btn.dataset.edit);
      setSection("manage");
    });
  });

  renderOverview();
}

function populateCameraSelects() {
  const liveSel = $("liveCameraSelect");
  const violCam = $("violCameraFilter");

  if (liveSel) {
    liveSel.innerHTML = state.cameras.map((c) => `<option value="${c.camera_code}">${c.camera_name} (${c.camera_code})</option>`).join("");
    if (!state.selectedLiveCameraId && state.cameras[0]) {
      state.selectedLiveCameraId = state.cameras[0].camera_code;
    }
    if (state.selectedLiveCameraId) {
      liveSel.value = state.selectedLiveCameraId;
    }
  }

  if (violCam) {
    violCam.innerHTML = `<option value="">T\u1ea5t c\u1ea3 camera</option>` + state.cameras.map((c) => `<option value="${c.camera_code}">${c.camera_name}</option>`).join("");
  }
}

async function loadCameras() {
  const res = await apiFetch("/api/cameras");
  state.cameras = Array.isArray(res?.cameras) ? res.cameras : [];
  renderCameras();
  renderManageCameraList();
  populateCameraSelects();
  renderLiveCamera();
  renderOverview();
}

function streamUrl(cameraCode) {
  const t = encodeURIComponent(token());
  return `/api/cameras/${encodeURIComponent(cameraCode)}/stream?token=${t}&ts=${Date.now()}`;
}

async function loadLiveViolations(cameraCode) {
  const list = $("liveViolations");
  if (!list) return;

  try {
    const data = await apiFetch(`/api/violations?camera_id=${encodeURIComponent(cameraCode)}&limit=10&offset=0`);
    const rows = Array.isArray(data?.violations) ? data.violations : [];
    list.innerHTML = rows.length ? rows.map((v) => `
      <div class="list-item">
        <div><strong>${v.plate_number || "--"}</strong></div>
        <div class="list-item__meta">${v.violation_type || "--"}</div>
        <div class="list-item__meta">${v.location_name || v.camera_name || cameraCode || "--"}</div>
        <div class="list-item__meta">${fmtDate(v.violation_time)}</div>
      </div>
    `).join("") : `<div class="list-item">Ch\u01b0a c\u00f3 vi ph\u1ea1m cho camera n\u00e0y.</div>`;
  } catch (e) {
    list.innerHTML = `<div class="list-item">Kh\u00f4ng t\u1ea3i \u0111\u01b0\u1ee3c vi ph\u1ea1m: ${e.message}</div>`;
  }
}

function renderLiveCamera() {
  const cam = state.cameras.find((c) => c.camera_code === state.selectedLiveCameraId) || null;
  $("liveName").textContent = cam?.camera_name || "--";
  $("liveCode").textContent = cam?.camera_code || "--";
  $("liveLocation").textContent = cam?.location_name || "--";
  $("liveStatus").textContent = cameraStatus(cam);
  $("liveLastSeen").textContent = fmtDate(cam?.last_seen || cam?.last_seen_at);
  $("liveHeroName").textContent = cam?.camera_name || "--";
  $("liveHeroLocation").textContent = cam?.location_name || "--";
  $("liveDeviceModel").textContent = cam?.device_model || "--";
  $("liveIpAddress").textContent = cam?.ip_address || "--";
  $("liveAiStatus").textContent = cam ? "AI pipeline sẵn sàng" : "--";

  const img = $("liveStreamImage");
  const ph = $("streamPlaceholder");
  const heroStatus = $("liveHeroStatus");
  const status = cameraStatus(cam);
  heroStatus.textContent = `Status: ${status}`;
  heroStatus.className = status === "ONLINE" ? "badge badge-online" : "badge badge-offline";

  if (cam && cam.stream_url) {
    img.src = streamUrl(cam.camera_code);
    img.style.display = "block";
    ph.style.display = "none";
    $("liveStreamState").textContent = "Proxy backend hoạt động";
    void loadLiveViolations(cam.camera_code);
  } else {
    img.removeAttribute("src");
    img.style.display = "none";
    ph.style.display = "block";
    $("liveStreamState").textContent = "Chưa có stream_url";
    $("liveViolations").innerHTML = `<div class="list-item">Camera n\u00e0y ch\u01b0a c\u00f3 stream_url ho\u1eb7c backend ch\u01b0a nh\u1eadn \u0111\u01b0\u1ee3c lu\u1ed3ng stream.</div>`;
  }
}

function buildViolFilterQuery() {
  const params = new URLSearchParams();
  params.set("limit", String(state.limit));
  params.set("offset", String((state.page - 1) * state.limit));

  const plate = ($("violPlateFilter")?.value || "").trim();
  const cameraId = ($("violCameraFilter")?.value || "").trim();
  const status = ($("violStatusFilter")?.value || "").trim();
  const dateFrom = ($("violDateFrom")?.value || "").trim();
  const dateTo = ($("violDateTo")?.value || "").trim();

  if (plate) params.set("plate_number", plate);
  if (cameraId) params.set("camera_id", cameraId);
  if (status) params.set("status", status);
  if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
  if (dateTo) params.set("date_to", new Date(dateTo).toISOString());

  return params.toString();
}

function renderViolations() {
  const body = $("violationsBody");
  const empty = $("violationsEmptyState");
  if (!body || !empty) return;

  const openCount = state.violations.filter((v) => {
    const status = String(v.status || "NEW").toUpperCase();
    return status === "NEW" || status === "REVIEWING";
  }).length;

  $("violSummaryVisible").textContent = String(state.violations.length);
  $("violSummaryOpen").textContent = String(openCount);
  $("violSummaryTotal").textContent = String(state.totalViolations);

  if (!state.violations.length) {
    body.innerHTML = "";
    empty.classList.remove("hidden");
    $("violPageInfo").textContent = `Trang ${state.page} - T\u1ed5ng ${state.totalViolations}`;
    renderOverview();
    return;
  }

  empty.classList.add("hidden");
  body.innerHTML = state.violations.map((v) => {
    const status = String(v.status || "NEW").toUpperCase();
    const cameraName = v.camera_name || v.camera_id || "--";
    return `
      <tr>
        <td>${v.full_image_url ? `<img class="thumb thumb--violation" src="${v.full_image_url}" alt="\u1ea2nh vi ph\u1ea1m">` : `<div class="thumb thumb--violation"></div>`}</td>
        <td>
          <div class="violation-cell-primary">
            <span class="violation-plate">${v.plate_number || "--"}</span>
            <span class="violation-subtext">${v.normalized_plate_number || "Bi\u1ec3n s\u1ed1 OCR"}</span>
          </div>
        </td>
        <td>
          <div class="violation-cell-primary">
            <strong>${fmtDate(v.violation_time)}</strong>
            <span class="violation-subtext">${v.created_at ? fmtDate(v.created_at) : "D\u1eef li\u1ec7u backend"}</span>
          </div>
        </td>
        <td>
          <div class="violation-camera">
            <strong>${cameraName}</strong>
            <span class="violation-subtext">${v.location_name || "--"}</span>
          </div>
        </td>
        <td><span class="violation-type-pill">${v.violation_type || "--"}</span></td>
        <td>${violationStatusBadge(status)}</td>
        <td><button class="link-btn" data-vid="${v.id}">Xem chi ti\u1ebft</button></td>
      </tr>
    `;
  }).join("");

  body.querySelectorAll("button[data-vid]").forEach((btn) => {
    btn.addEventListener("click", () => openViolationDetail(Number(btn.dataset.vid)));
  });

  $("violPageInfo").textContent = `Trang ${state.page} - T\u1ed5ng ${state.totalViolations}`;
  renderOverview();
}

async function loadViolations() {
  const data = await apiFetch(`/api/violations?${buildViolFilterQuery()}`);
  state.violations = Array.isArray(data?.violations) ? data.violations : [];
  state.totalViolations = Number(data?.total || 0);
  renderViolations();
}

function detailMetaCard(label, value, options = {}) {
  const cardClass = ["meta-card", options.cardClass].filter(Boolean).join(" ");
  const valueClass = ["meta-value", options.valueClass].filter(Boolean).join(" ");
  return `<div class="${cardClass}"><div class="meta-label">${label}</div><div class="${valueClass}">${value || "--"}</div></div>`;
}

function setDetailImage(imgId, fallbackId, src) {
  const img = $(imgId);
  const fallback = $(fallbackId);
  if (!img || !fallback) return;

  if (src) {
    img.src = src;
    img.style.display = "block";
    fallback.classList.add("hidden");
  } else {
    img.removeAttribute("src");
    img.style.display = "none";
    fallback.classList.remove("hidden");
  }
}

async function openViolationDetail(id) {
  const data = await apiFetch(`/api/violations/${id}`);
  const v = data?.violation;
  if (!v) return;

  const plateNumber = v.plate_number || v.normalized_plate_number || "--";
  const normalizedPlate = v.normalized_plate_number || "Kh\u00f4ng c\u00f3 chu\u1ea9n h\u00f3a OCR";
  const violationStatus = String(v.status || "NEW").toUpperCase();
  const cameraLabel = v.camera_name || v.camera_id || "--";
  const ocrConfidence = v.ocr_confidence === null || v.ocr_confidence === undefined || v.ocr_confidence === ""
    ? "--"
    : `${v.ocr_confidence}`;

  setDetailImage("dFullImage", "dFullFallback", v.full_image_url || v.location_snapshot || "");
  setDetailImage("dVehicleImage", "dVehicleFallback", v.vehicle_crop_url || "");
  setDetailImage("dPlateImage", "dPlateFallback", v.plate_crop_url || "");

  $("detailPlateHero").textContent = plateNumber;
  $("detailPlateSubline").textContent = normalizedPlate !== plateNumber
    ? `OCR chu\u1ea9n h\u00f3a: ${normalizedPlate}`
    : "D\u1eef li\u1ec7u OCR \u0111\u1ed3ng b\u1ed9 t\u1eeb backend";
  $("detailCameraHero").textContent = cameraLabel;
  $("detailStatusHero").innerHTML = violationStatusBadge(violationStatus);

  $("detailMeta").innerHTML = [
    detailMetaCard("Bi\u1ec3n s\u1ed1", plateNumber, {
      cardClass: "meta-card--plate",
      valueClass: "meta-value--plate"
    }),
    detailMetaCard("Lo\u1ea1i vi ph\u1ea1m", v.violation_type || "--"),
    detailMetaCard("Tr\u1ea1ng th\u00e1i", violationStatusBadge(violationStatus), {
      cardClass: "meta-card--status"
    }),
    detailMetaCard("Th\u1eddi gian", fmtDate(v.violation_time), {
      valueClass: "meta-value--mono"
    }),
    detailMetaCard("\u0110\u1ecba \u0111i\u1ec3m", v.location_name || v.location_snapshot || "--", {
      cardClass: "meta-card--wide"
    }),
    detailMetaCard("Camera", cameraLabel),
    detailMetaCard("Tr\u1ea1ng th\u00e1i \u0111\u00e8n", (v.light_state || "--").toString().toUpperCase()),
    detailMetaCard("\u0110\u1ed9 tin c\u1eady OCR", ocrConfidence, {
      valueClass: "meta-value--mono"
    })
  ].join("");
  $("violationModal").classList.remove("hidden");
}

function closeViolationDetail() {
  $("violationModal").classList.add("hidden");
}

function cameraPayloadFromForm() {
  return {
    camera_code: ($("fCameraCode").value || "").trim(),
    camera_name: ($("fCameraName").value || "").trim(),
    stream_url: ($("fStreamUrl").value || "").trim(),
    location_name: ($("fLocationName").value || "").trim(),
    latitude: $("fLatitude").value ? Number($("fLatitude").value) : null,
    longitude: $("fLongitude").value ? Number($("fLongitude").value) : null,
    install_position: ($("fInstallPosition").value || "").trim(),
    device_model: ($("fDeviceModel").value || "").trim(),
    ip_address: ($("fIpAddress").value || "").trim(),
    is_active: Number($("fIsActive").value || "1")
  };
}

function resetCameraForm() {
  state.editingCameraId = "";
  $("cameraFormId").value = "";
  $("cameraForm").reset();
  $("fIsActive").value = "1";
  setManageFeedback("", "info");
  syncManageFormState();
}

function beginEditCamera(cameraCode) {
  const cam = state.cameras.find((c) => c.camera_code === cameraCode);
  if (!cam) return;

  state.editingCameraId = cam.camera_code;
  $("cameraFormId").value = cam.camera_code;
  $("fCameraCode").value = cam.camera_code || "";
  $("fCameraName").value = cam.camera_name || "";
  $("fStreamUrl").value = cam.stream_url || "";
  $("fLocationName").value = cam.location_name || "";
  $("fLatitude").value = cam.latitude ?? "";
  $("fLongitude").value = cam.longitude ?? "";
  $("fInstallPosition").value = cam.install_position || "";
  $("fDeviceModel").value = cam.device_model || "";
  $("fIpAddress").value = cam.ip_address || "";
  $("fIsActive").value = String(cam.is_active ?? 1);
  syncManageFormState();
  setManageFeedback(`\u0110ang ch\u1ec9nh s\u1eeda camera ${cam.camera_code}.`, "info");
}

function renderManageCameraList() {
  const body = $("manageCamerasBody");
  const empty = $("manageEmptyState");
  if (!body || !empty) return;

  if (!state.cameras.length) {
    body.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");

  body.innerHTML = state.cameras.map((cam) => `
    <tr>
      <td><strong>${cam.camera_name || "--"}</strong><span>${cam.location_name || "--"}</span></td>
      <td>${cam.camera_code || "--"}</td>
      <td>${cam.stream_url ? `<span class="stream-chip">Đã cấu hình</span>` : `<span class="stream-chip">Chưa có stream</span>`}</td>
      <td>${badgeStatus(cameraStatus(cam))}</td>
      <td class="row-actions">
        <button class="link-btn" data-medit="${cam.camera_code}">S\u1eeda</button>
        <button class="link-btn danger" data-mdel="${cam.camera_code}">X\u00f3a</button>
      </td>
    </tr>
  `).join("");

  body.querySelectorAll("button[data-medit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      beginEditCamera(btn.dataset.medit);
      setSection("manage");
    });
  });

  body.querySelectorAll("button[data-mdel]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.mdel;
      if (!window.confirm(`X\u00f3a camera ${id}?`)) return;
      await apiFetch(`/api/cameras/${encodeURIComponent(id)}`, { method: "DELETE" });
      showToast("\u0110\u00e3 x\u00f3a camera");
      setManageFeedback(`\u0110\u00e3 x\u00f3a camera ${id}.`, "success");
      await loadCameras();
    });
  });
}

function applyCameraStatusUpdate(payload) {
  if (!payload?.camera_code) return;
  const idx = state.cameras.findIndex((c) => c.camera_code === payload.camera_code);
  if (idx < 0) return;

  state.cameras[idx] = {
    ...state.cameras[idx],
    status: String(payload.status || "ONLINE").toLowerCase(),
    last_seen: payload.last_seen || payload.last_seen_at || state.cameras[idx].last_seen,
    ip_address: payload.ip_address || state.cameras[idx].ip_address
  };

  pushEventFeed("Camera c\u1eadp nh\u1eadt tr\u1ea1ng th\u00e1i", `${payload.camera_code} - ${String(payload.status || "ONLINE").toUpperCase()}`);
  renderCameras();
  renderManageCameraList();
  if (state.selectedLiveCameraId === payload.camera_code) {
    renderLiveCamera();
  }
}

function applyViolationCreated(payload) {
  if (!payload || !payload.id) return;

  if (state.page === 1) {
    state.violations = [payload, ...state.violations].slice(0, state.limit);
    state.totalViolations += 1;
    renderViolations();
  }

  pushEventFeed("Vi ph\u1ea1m m\u1edbi", `${payload.plate_number || "--"} - ${payload.violation_type || "--"}`);
  if (state.selectedLiveCameraId && String(payload.camera_id || payload.camera_code || "") === state.selectedLiveCameraId) {
    void loadLiveViolations(state.selectedLiveCameraId);
  }
}

function syncHealthBadges() {
  const backendText = state.backendOnline ? "Backend: online" : "Backend: offline";
  const backendClass = state.backendOnline ? "badge badge-online" : "badge badge-offline";
  $("backendHealth").textContent = backendText;
  $("backendHealth").className = backendClass;
  $("backendHealthSide").textContent = state.backendOnline ? "Online" : "Offline";
  $("backendHealthSide").className = state.backendOnline ? "badge badge-online" : "badge badge-offline";

  const realtimeText = state.realtimeConnected ? "Realtime: connected" : "Realtime: disconnected";
  const realtimeClass = state.realtimeConnected ? "badge badge-online" : "badge badge-offline";
  $("realtimeHealth").textContent = realtimeText;
  $("realtimeHealth").className = realtimeClass;
  $("realtimeHealthSide").textContent = state.realtimeConnected ? "Live" : "Waiting";
  $("realtimeHealthSide").className = realtimeClass;

  renderOverview();
}

function connectRealtime() {
  if (state.sse) {
    state.sse.close();
    state.sse = null;
  }

  const t = token();
  if (!t) return;

  const es = new EventSource(`/api/realtime/events?token=${encodeURIComponent(t)}`);
  state.sse = es;
  state.realtimeConnected = false;
  syncHealthBadges();

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data || "{}");
      state.realtimeConnected = true;
      syncHealthBadges();

      if (data.type === "camera_status_updated") applyCameraStatusUpdate(data.payload);
      if (data.type === "violation_created") applyViolationCreated(data.payload);
    } catch (_) {
      // ignore invalid event payload
    }
  };

  es.onerror = () => {
    state.realtimeConnected = false;
    syncHealthBadges();
    es.close();
    setTimeout(connectRealtime, state.sseRetryMs);
  };
}

async function checkHealth() {
  try {
    const data = await apiFetch("/api/health");
    state.backendOnline = Boolean(data?.ok);
  } catch (_) {
    state.backendOnline = false;
  }
  syncHealthBadges();
}

function bindEvents() {
  $("btnLogout").addEventListener("click", () => {
    localStorage.removeItem(TOKEN_KEY);
    window.location.replace("/login");
  });

  $("cameraSearch").addEventListener("input", renderCameras);
  $("cameraStatusFilter").addEventListener("change", renderCameras);

  $("liveCameraSelect").addEventListener("change", () => {
    state.selectedLiveCameraId = $("liveCameraSelect").value;
    renderLiveCamera();
  });

  $("btnApplyViolFilters").addEventListener("click", async () => {
    state.page = 1;
    await loadViolations();
  });

  $("btnPrevPage").addEventListener("click", async () => {
    if (state.page <= 1) return;
    state.page -= 1;
    await loadViolations();
  });

  $("btnNextPage").addEventListener("click", async () => {
    const maxPage = Math.max(1, Math.ceil(state.totalViolations / state.limit));
    if (state.page >= maxPage) return;
    state.page += 1;
    await loadViolations();
  });

  $("btnCloseModal").addEventListener("click", closeViolationDetail);
  $("modalBackdrop").addEventListener("click", closeViolationDetail);
  $("btnResetForm").addEventListener("click", resetCameraForm);

  $("cameraForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = cameraPayloadFromForm();
    setManageFeedback("", "info");
    if (!payload.camera_code || !payload.camera_name) {
      setManageFeedback("camera_code v\u00e0 camera_name l\u00e0 b\u1eaft bu\u1ed9c.", "error");
      showToast("camera_code v\u00e0 camera_name l\u00e0 b\u1eaft bu\u1ed9c");
      return;
    }

    try {
      if (state.editingCameraId) {
        await apiFetch(`/api/cameras/${encodeURIComponent(state.editingCameraId)}`, {
          method: "PUT",
          body: JSON.stringify(payload)
        });
        showToast("\u0110\u00e3 c\u1eadp nh\u1eadt camera");
        setManageFeedback(`\u0110\u00e3 c\u1eadp nh\u1eadt camera ${payload.camera_code}.`, "success");
      } else {
        await apiFetch("/api/cameras", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        showToast("\u0110\u00e3 t\u1ea1o camera");
        setManageFeedback(`\u0110\u00e3 t\u1ea1o camera ${payload.camera_code}.`, "success");
      }

      resetCameraForm();
      await loadCameras();
    } catch (error) {
      setManageFeedback(`Kh\u00f4ng th\u1ec3 l\u01b0u camera: ${error.message}`, "error");
      showToast("Kh\u00f4ng l\u01b0u \u0111\u01b0\u1ee3c camera");
    }
  });
}

async function bootstrap() {
  if (!ensureAuth()) return;

  attachSidebarNavigation();
  bindEvents();
  setSection("overview");
  renderOverview();
  syncManageFormState();
  await checkHealth();
  await loadCameras();
  await loadViolations();
  connectRealtime();
  pushEventFeed("Dashboard s\u1eb5n s\u00e0ng", "\u0110\u00e3 t\u1ea3i d\u1eef li\u1ec7u camera v\u00e0 vi ph\u1ea1m t\u1eeb backend.");

  setInterval(() => void checkHealth(), 30000);
  setInterval(() => {
    if (state.backendOnline) {
      void loadCameras();
    }
  }, 60000);
}

void bootstrap();
