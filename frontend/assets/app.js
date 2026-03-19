const backendBase = normalizeBackendBase(window.APP_CONFIG.apiBaseUrl || "");
const apiRoot = `${backendBase}/api`;
const zoneColors = {
    detection: "#56c1ff",
    stop_line: "#ffae57",
    violation_zone: "#ff6f61",
    roi: "#4ed28a",
};

const state = {
    cameras: [],
    selectedCameraId: null,
    overlayEnabled: true,
    camera: null,
    liveOverlay: null,
    zones: [],
    streamStatus: null,
    refreshTimer: null,
    eventSource: null,
};

const elements = {
    cameraList: document.getElementById("cameraList"),
    cameraCount: document.getElementById("cameraCount"),
    cameraTitle: document.getElementById("cameraTitle"),
    cameraSubtitle: document.getElementById("cameraSubtitle"),
    streamImage: document.getElementById("streamImage"),
    overlayCanvas: document.getElementById("overlayCanvas"),
    viewerEmpty: document.getElementById("viewerEmpty"),
    toggleOverlayBtn: document.getElementById("toggleOverlayBtn"),
    reloadLiveBtn: document.getElementById("reloadLiveBtn"),
    refreshCamerasBtn: document.getElementById("refreshCamerasBtn"),
    snapshotLink: document.getElementById("snapshotLink"),
    apiHealthLink: document.getElementById("apiHealthLink"),
    onlineBadge: document.getElementById("onlineBadge"),
    streamBadge: document.getElementById("streamBadge"),
    streamWarning: document.getElementById("streamWarning"),
    lightState: document.getElementById("lightState"),
    detectionCount: document.getElementById("detectionCount"),
    frameSize: document.getElementById("frameSize"),
    capturedAt: document.getElementById("capturedAt"),
    qualityScore: document.getElementById("qualityScore"),
    processingMs: document.getElementById("processingMs"),
    cameraIp: document.getElementById("cameraIp"),
    cameraStreamUrl: document.getElementById("cameraStreamUrl"),
    workerState: document.getElementById("workerState"),
    retryCount: document.getElementById("retryCount"),
    lastFrameAt: document.getElementById("lastFrameAt"),
    lastError: document.getElementById("lastError"),
    zoneCount: document.getElementById("zoneCount"),
    zoneLegend: document.getElementById("zoneLegend"),
};

bootstrap().catch((error) => {
    renderCameraError(`Khoi dong web that bai: ${error.message}`);
});

async function bootstrap() {
    elements.apiHealthLink.href = `${backendBase}/health`;
    bindEvents();
    await loadCameras();
}

function bindEvents() {
    elements.refreshCamerasBtn.addEventListener("click", () => {
        loadCameras().catch((error) => {
            renderCameraError(`Tai lai camera that bai: ${error.message}`);
        });
    });

    elements.reloadLiveBtn.addEventListener("click", () => {
        if (!state.selectedCameraId) {
            return;
        }
        loadSelectedCamera(state.selectedCameraId, { resetStream: true }).catch((error) => {
            showWarning(`Tai lai live that bai: ${error.message}`);
        });
    });

    elements.toggleOverlayBtn.addEventListener("click", () => {
        state.overlayEnabled = !state.overlayEnabled;
        elements.toggleOverlayBtn.textContent = `Overlay: ${state.overlayEnabled ? "ON" : "OFF"}`;
        elements.overlayCanvas.style.display = state.overlayEnabled ? "block" : "none";
        drawOverlay();
    });

    elements.streamImage.addEventListener("load", () => {
        elements.viewerEmpty.hidden = true;
        syncCanvasSize();
        drawOverlay();
    });

    elements.streamImage.addEventListener("error", () => {
        showWarning("Khong mo duoc stream qua backend. Kiem tra backend dang chay va camera co tra MJPEG hay khong.");
    });

    window.addEventListener("resize", () => {
        syncCanvasSize();
        drawOverlay();
    });
}

async function loadCameras() {
    const cameras = await fetchJson("/cameras");
    state.cameras = Array.isArray(cameras) ? cameras : [];
    renderCameraList();

    if (!state.cameras.length) {
        renderCameraError("Backend da len nhung chua co camera nao trong danh sach.");
        return;
    }

    const nextCameraId = state.selectedCameraId && state.cameras.some((camera) => camera.camera_id === state.selectedCameraId)
        ? state.selectedCameraId
        : state.cameras[0].camera_id;

    await loadSelectedCamera(nextCameraId, { resetStream: true });
}

function renderCameraList() {
    elements.cameraCount.textContent = String(state.cameras.length);
    elements.cameraList.innerHTML = "";

    if (!state.cameras.length) {
        elements.cameraList.innerHTML = '<p class="empty-state">Khong co camera nao.</p>';
        return;
    }

    for (const camera of state.cameras) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = `camera-card${camera.camera_id === state.selectedCameraId ? " is-active" : ""}`;
        card.innerHTML = `
            <h3>${escapeHtml(camera.camera_name || `Camera ${camera.camera_id}`)}</h3>
            <p>${escapeHtml(camera.location || "Chua cau hinh")}</p>
            <p>${escapeHtml(camera.ip_address || "Chua co IP")} | ${camera.online ? "online" : "offline"}</p>
        `;
        card.addEventListener("click", () => {
            loadSelectedCamera(camera.camera_id, { resetStream: true }).catch((error) => {
                showWarning(`Khong tai duoc camera ${camera.camera_id}: ${error.message}`);
            });
        });
        elements.cameraList.appendChild(card);
    }
}

async function loadSelectedCamera(cameraId, options = {}) {
    state.selectedCameraId = cameraId;
    renderCameraList();
    closeEventSource();
    stopAutoRefresh();

    const [camera, liveView, zones, streamStatus] = await Promise.all([
        fetchJson(`/cameras/${cameraId}`),
        fetchJson(`/cameras/${cameraId}/live-view`),
        fetchJson(`/cameras/${cameraId}/zones`).catch(() => []),
        fetchJson(`/streams/${cameraId}`).catch(() => null),
    ]);

    state.camera = camera;
    state.liveOverlay = liveView.overlay || {};
    state.zones = Array.isArray(zones) ? zones : [];
    state.streamStatus = streamStatus;

    renderCameraMeta();
    renderHealth();
    renderZones();
    connectLiveOverlay(cameraId);

    if (options.resetStream) {
        const streamUrl = `${apiRoot}/cameras/${cameraId}/stream?ts=${Date.now()}`;
        elements.streamImage.src = streamUrl;
        elements.snapshotLink.href = `${apiRoot}/cameras/${cameraId}/snapshot`;
        elements.viewerEmpty.hidden = false;
    }

    syncCanvasSize();
    drawOverlay();
    startAutoRefresh(cameraId);
}

function renderCameraMeta() {
    const camera = state.camera || {};
    const overlay = state.liveOverlay || {};
    elements.cameraTitle.textContent = camera.camera_name || `Camera ${camera.camera_id || "-"}`;
    elements.cameraSubtitle.textContent = [
        camera.location || "Chua cau hinh vi tri",
        camera.device_name || camera.tb_device_name || "Khong co device label",
    ].join(" | ");

    setBadge(elements.onlineBadge, camera.online ? "online" : "offline", camera.online ? "good" : "bad");
    setBadge(
        elements.streamBadge,
        camera.stream_connected ? "stream connected" : (camera.stream_running ? "dang doi frame" : "worker dung"),
        camera.stream_connected ? "good" : (camera.stream_running ? "warn" : "bad")
    );

    elements.lightState.textContent = overlay.traffic_light_state || "-";
    elements.detectionCount.textContent = String(overlay.detection_count || 0);
    elements.frameSize.textContent = overlay.frame_width && overlay.frame_height
        ? `${overlay.frame_width} x ${overlay.frame_height}`
        : "-";
    elements.capturedAt.textContent = formatDate(overlay.captured_at || overlay.updated_at);
    elements.qualityScore.textContent = overlay.quality_score ?? "-";
    elements.processingMs.textContent = overlay.processing_ms ?? "-";
}

function renderHealth() {
    const camera = state.camera || {};
    const streamStatus = state.streamStatus || {};
    elements.cameraIp.textContent = camera.ip_address || "-";
    elements.cameraStreamUrl.textContent = camera.stream_url || "-";
    elements.workerState.textContent = streamStatus.running
        ? (streamStatus.connected ? "running + connected" : "running + waiting")
        : "stopped";
    elements.retryCount.textContent = String(streamStatus.retry_count || 0);
    elements.lastFrameAt.textContent = formatDate(streamStatus.last_frame_at || camera.stream_last_frame_at);
    elements.lastError.textContent = streamStatus.last_error || camera.stream_last_error || "-";

    if (streamStatus.last_error) {
        showWarning(`Backend khong keo duoc stream camera: ${streamStatus.last_error}`);
    } else if (!camera.stream_connected && camera.stream_running) {
        showWarning("Worker dang chay nhung chua nhan duoc frame tu camera.");
    } else {
        hideWarning();
    }
}

function renderZones() {
    elements.zoneCount.textContent = String(state.zones.length);
    elements.zoneLegend.innerHTML = "";

    if (!state.zones.length) {
        elements.zoneLegend.innerHTML = '<p class="empty-state">Chua co zone nao cho camera nay.</p>';
        return;
    }

    for (const zone of state.zones) {
        const row = document.createElement("div");
        row.className = "zone-item";
        const color = zoneColors[zone.zone_type] || "#ffffff";
        row.innerHTML = `
            <span class="zone-swatch" style="color:${color}"></span>
            <div>
                <strong>${escapeHtml(zone.zone_name || zone.zone_type || "zone")}</strong>
                <div class="muted">${escapeHtml(zone.zone_type || "unknown")} | ${zone.width}x${zone.height}</div>
            </div>
        `;
        elements.zoneLegend.appendChild(row);
    }
}

function connectLiveOverlay(cameraId) {
    const stream = new EventSource(`${apiRoot}/cameras/${cameraId}/live-view/sse`);
    state.eventSource = stream;

    stream.onmessage = (event) => {
        try {
            state.liveOverlay = JSON.parse(event.data);
            renderCameraMeta();
            drawOverlay();
        } catch (error) {
            console.error("Invalid live-view SSE payload", error);
        }
    };

    stream.onerror = () => {
        showWarning("Mat ket noi SSE overlay. Web se tu dong tai lai trang thai dinh ky.");
    };
}

function closeEventSource() {
    if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
    }
}

function startAutoRefresh(cameraId) {
    stopAutoRefresh();
    state.refreshTimer = window.setInterval(async () => {
        try {
            const [camera, streamStatus] = await Promise.all([
                fetchJson(`/cameras/${cameraId}`),
                fetchJson(`/streams/${cameraId}`).catch(() => null),
            ]);
            state.camera = camera;
            state.streamStatus = streamStatus;
            renderCameraMeta();
            renderHealth();
        } catch (error) {
            showWarning(`Khong refresh duoc health: ${error.message}`);
        }
    }, 5000);
}

function stopAutoRefresh() {
    if (state.refreshTimer) {
        window.clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

function drawOverlay() {
    const canvas = elements.overlayCanvas;
    const context = canvas.getContext("2d");
    if (!context) {
        return;
    }

    syncCanvasSize();
    context.clearRect(0, 0, canvas.width, canvas.height);

    if (!state.overlayEnabled) {
        return;
    }

    const overlay = state.liveOverlay || {};
    const frameWidth = Number(overlay.frame_width || 0);
    const frameHeight = Number(overlay.frame_height || 0);
    if (!frameWidth || !frameHeight) {
        return;
    }

    const scaleX = canvas.width / frameWidth;
    const scaleY = canvas.height / frameHeight;
    const lineScale = Math.max(2, canvas.width / 540);
    context.lineWidth = lineScale;
    context.font = `${Math.max(16, canvas.width / 45)}px Segoe UI`;

    for (const zone of state.zones) {
        const color = zoneColors[zone.zone_type] || "#ffffff";
        context.strokeStyle = color;
        context.fillStyle = hexToRgba(color, 0.12);
        context.fillRect(zone.x * scaleX, zone.y * scaleY, zone.width * scaleX, zone.height * scaleY);
        context.strokeRect(zone.x * scaleX, zone.y * scaleY, zone.width * scaleX, zone.height * scaleY);
        drawLabel(context, zone.zone_name || zone.zone_type || "zone", zone.x * scaleX, Math.max(18, zone.y * scaleY - 8), color);
    }

    for (const detection of overlay.detections || []) {
        const bbox = normalizeBbox(detection.bbox);
        if (!bbox) {
            continue;
        }
        const x = bbox.x1 * scaleX;
        const y = bbox.y1 * scaleY;
        const w = (bbox.x2 - bbox.x1) * scaleX;
        const h = (bbox.y2 - bbox.y1) * scaleY;
        const color = detection.is_violation ? "#ff6f61" : "#56c1ff";

        context.strokeStyle = color;
        context.fillStyle = hexToRgba(color, 0.1);
        context.fillRect(x, y, w, h);
        context.strokeRect(x, y, w, h);

        const labelParts = [];
        if (detection.plate_text) {
            labelParts.push(detection.plate_text);
        }
        if (typeof detection.confidence === "number") {
            labelParts.push(`${Math.round(detection.confidence * 100)}%`);
        }
        if (detection.crossed_stop_line) {
            labelParts.push("cross");
        }
        drawLabel(context, labelParts.join(" | ") || "plate", x, Math.max(20, y - 8), color);
    }
}

function drawLabel(context, text, x, y, color) {
    if (!text) {
        return;
    }
    const paddingX = 10;
    const paddingY = 6;
    const metrics = context.measureText(text);
    const width = metrics.width + paddingX * 2;
    const height = parseInt(context.font, 10) + paddingY * 2;
    context.fillStyle = color;
    context.fillRect(x, y - height, width, height);
    context.fillStyle = "#081018";
    context.fillText(text, x + paddingX, y - paddingY);
}

function syncCanvasSize() {
    const image = elements.streamImage;
    const canvas = elements.overlayCanvas;
    const width = image.clientWidth || image.parentElement.clientWidth;
    const height = image.clientHeight || image.parentElement.clientHeight;

    if (!width || !height) {
        return;
    }

    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
}

async function fetchJson(path) {
    const response = await fetch(`${apiRoot}${path}`, {
        headers: { Accept: "application/json" },
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`${response.status} ${text || response.statusText}`);
    }
    return response.json();
}

function renderCameraError(message) {
    elements.cameraTitle.textContent = "Khong the tai camera";
    elements.cameraSubtitle.textContent = message;
    elements.cameraList.innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
    showWarning(message);
}

function showWarning(message) {
    elements.streamWarning.hidden = false;
    elements.streamWarning.textContent = message;
}

function hideWarning() {
    elements.streamWarning.hidden = true;
    elements.streamWarning.textContent = "";
}

function setBadge(element, text, tone) {
    element.textContent = text;
    element.className = `badge badge--${tone}`;
}

function normalizeBackendBase(rawUrl) {
    let value = String(rawUrl || "").trim().replace(/\/+$/, "");
    if (!value) {
        value = `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    if (value.endsWith("/api")) {
        value = value.slice(0, -4);
    }
    return value;
}

function normalizeBbox(bbox) {
    if (!bbox) {
        return null;
    }
    if (Array.isArray(bbox) && bbox.length >= 4) {
        return { x1: Number(bbox[0]), y1: Number(bbox[1]), x2: Number(bbox[2]), y2: Number(bbox[3]) };
    }
    if (typeof bbox === "object") {
        return { x1: Number(bbox.x1), y1: Number(bbox.y1), x2: Number(bbox.x2), y2: Number(bbox.y2) };
    }
    return null;
}

function formatDate(value) {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }
    return date.toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function hexToRgba(hex, alpha) {
    const normalized = hex.replace("#", "");
    const value = normalized.length === 3
        ? normalized.split("").map((char) => char + char).join("")
        : normalized;
    const int = Number.parseInt(value, 16);
    const r = (int >> 16) & 255;
    const g = (int >> 8) & 255;
    const b = int & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
