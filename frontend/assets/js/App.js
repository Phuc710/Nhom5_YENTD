(function () {
    const config = window.APP_CONFIG || {};
    const apiBase = String(config.apiBaseUrl || "").replace(/\/$/, "");
    const apiRoot = apiBase ? `${apiBase}/api` : "/api";
    const refreshMs = 10000;

    const state = {
        cameras: [],
        route: { name: "dashboard", cameraId: null, search: new URLSearchParams(window.location.search) },
        currentCameraId: null,
        overlayEnabled: true,
        globalEvents: null,
        detailEvents: null,
        refreshTimer: null,
        refreshQueued: false,
        overlayState: null,
    };

    const els = {};

    document.addEventListener("DOMContentLoaded", init);

    function init() {
        bindElements();
        bindEvents();
        syncStaticSettings();
        ensureLeadingRoute();
        openGlobalRealtime();
        handleRoute();
    }

    function bindElements() {
        els.views = {
            dashboard: document.getElementById("view-dashboard"),
            cameras: document.getElementById("view-cameras"),
            detail: document.getElementById("view-camera-detail"),
            violations: document.getElementById("view-violations"),
            settings: document.getElementById("view-settings"),
        };

        els.navLinks = Array.from(document.querySelectorAll(".nav-link"));
        els.navButtons = Array.from(document.querySelectorAll("[data-nav]"));
        els.serverIp = document.getElementById("server-ip");
        els.apiHealthLink = document.getElementById("apiHealthLink");
        els.cameraGrid = document.getElementById("cameraGrid");
        els.dashboardCameraGrid = document.getElementById("dashboardCameraGrid");
        els.recentViolations = document.getElementById("recent-violations-list");
        els.trendChart = document.getElementById("hourly-trend-chart");
        els.statTotalToday = document.getElementById("stat-total-today");
        els.statOnlineCameras = document.getElementById("stat-online-cameras");
        els.statAiStatus = document.getElementById("stat-ai-status");
        els.refreshViolationsBtn = document.getElementById("refreshViolationsBtn");
        els.applyViolationFiltersBtn = document.getElementById("applyViolationFiltersBtn");
        els.filterPlate = document.getElementById("filter-plate");
        els.filterCamera = document.getElementById("filter-camera");
        els.filterDate = document.getElementById("filter-date");
        els.violationsList = document.getElementById("violations-list");

        els.cameraTitle = document.getElementById("cameraTitle");
        els.cameraSubtitle = document.getElementById("cameraSubtitle");
        els.toggleOverlayBtn = document.getElementById("toggleOverlayBtn");
        els.reloadLiveBtn = document.getElementById("reloadLiveBtn");
        els.streamImage = document.getElementById("streamImage");
        els.overlayCanvas = document.getElementById("overlayCanvas");
        els.viewerEmpty = document.getElementById("viewerEmpty");
        els.onlineBadge = document.getElementById("onlineBadge");
        els.streamBadge = document.getElementById("streamBadge");
        els.streamWarning = document.getElementById("streamWarning");
        els.lightState = document.getElementById("lightState");
        els.detectionCount = document.getElementById("detectionCount");
        els.frameSize = document.getElementById("frameSize");
        els.capturedAt = document.getElementById("capturedAt");
        els.cameraIp = document.getElementById("cameraIp");
        els.cameraStreamUrl = document.getElementById("cameraStreamUrl");
        els.workerState = document.getElementById("workerState");
        els.retryCount = document.getElementById("retryCount");
        els.lastFrameAt = document.getElementById("lastFrameAt");
        els.lastError = document.getElementById("lastError");
        els.zoneCount = document.getElementById("zoneCount");
        els.zoneLegend = document.getElementById("zoneLegend");
        els.cameraRecentViolations = document.getElementById("cameraRecentViolations");
        els.cameraViolationsNavBtn = document.getElementById("cameraViolationsNavBtn");

        els.settingsCurrentPath = document.getElementById("settingsCurrentPath");
        els.settingsApiRoot = document.getElementById("settingsApiRoot");
        els.settingsRefreshInterval = document.getElementById("settingsRefreshInterval");

        els.evidenceModal = document.getElementById("evidenceModal");
        els.modalFullImage = document.getElementById("modalFullImage");
        els.modalPlateImage = document.getElementById("modalPlateImage");
        els.modalDetails = document.getElementById("modalDetails");
        els.closeEvidenceModalBtn = document.getElementById("closeEvidenceModalBtn");
    }

    function bindEvents() {
        window.addEventListener("popstate", handleRoute);
        document.addEventListener("click", onDocumentClick);
        els.toggleOverlayBtn?.addEventListener("click", toggleOverlay);
        els.reloadLiveBtn?.addEventListener("click", reloadCurrentCameraStream);
        els.refreshViolationsBtn?.addEventListener("click", () => loadViolationsView(true));
        els.applyViolationFiltersBtn?.addEventListener("click", applyViolationFilters);
        els.cameraViolationsNavBtn?.addEventListener("click", () => {
            if (state.currentCameraId) {
                navigate(`/violations?camera_id=${state.currentCameraId}`);
            }
        });
        els.closeEvidenceModalBtn?.addEventListener("click", closeEvidenceModal);
        els.evidenceModal?.addEventListener("click", (event) => {
            if (event.target === els.evidenceModal) {
                closeEvidenceModal();
            }
        });
        window.addEventListener("resize", () => drawOverlay(state.overlayState));
    }

    function onDocumentClick(event) {
        const navTarget = event.target.closest("[data-nav]");
        if (navTarget) {
            event.preventDefault();
            navigate(navTarget.getAttribute("data-nav"));
            return;
        }

        const cameraLink = event.target.closest("[data-camera-path]");
        if (cameraLink) {
            event.preventDefault();
            navigate(cameraLink.getAttribute("data-camera-path"));
            return;
        }

        const evidenceButton = event.target.closest("[data-evidence]");
        if (evidenceButton) {
            event.preventDefault();
            openEvidenceModal(JSON.parse(evidenceButton.getAttribute("data-evidence")));
            return;
        }

        const reloadButton = event.target.closest("[data-reload-camera]");
        if (reloadButton) {
            event.preventDefault();
            reloadCameraStream(Number(reloadButton.getAttribute("data-reload-camera")));
        }
    }

    function ensureLeadingRoute() {
        const currentPath = normalizePath(window.location.pathname || config.currentPath || "/");
        if (currentPath === "/") {
            history.replaceState({}, "", `/dashboard${window.location.search || ""}`);
        }
    }

    function navigate(path) {
        if (!path) {
            return;
        }
        const url = new URL(path, window.location.origin);
        const next = `${normalizePath(url.pathname)}${url.search}`;
        const current = `${normalizePath(window.location.pathname)}${window.location.search}`;
        if (next === current) {
            handleRoute();
            return;
        }
        history.pushState({}, "", next);
        handleRoute();
    }

    function normalizePath(pathname) {
        const path = `/${String(pathname || "").replace(/^\/+/, "")}`.replace(/\/{2,}/g, "/");
        return path.length > 1 ? path.replace(/\/$/, "") : path;
    }

    function parseRoute() {
        const pathname = normalizePath(window.location.pathname || "/dashboard");
        const detailMatch = pathname.match(/^\/cameras\/(\d+)(?:-[a-z0-9-]+)?$/i);
        const search = new URLSearchParams(window.location.search);

        if (pathname === "/" || pathname === "/dashboard") {
            return { name: "dashboard", cameraId: null, search };
        }
        if (pathname === "/cameras") {
            return { name: "cameras", cameraId: null, search };
        }
        if (detailMatch) {
            return { name: "detail", cameraId: Number(detailMatch[1]), search };
        }
        if (pathname === "/violations") {
            return { name: "violations", cameraId: null, search };
        }
        if (pathname === "/settings") {
            return { name: "settings", cameraId: null, search };
        }
        return { name: "dashboard", cameraId: null, search };
    }

    async function handleRoute() {
        state.route = parseRoute();
        state.currentCameraId = state.route.cameraId;
        state.overlayState = null;
        document.title = config.appTitle || "Camera AI";
        closeDetailRealtime();
        clearRefreshTimer();
        renderActiveNav();
        showView(state.route.name);

        if (state.route.name === "dashboard") {
            await loadDashboardView();
            scheduleCurrentViewRefresh();
            return;
        }
        if (state.route.name === "cameras") {
            await loadCamerasView();
            scheduleCurrentViewRefresh();
            return;
        }
        if (state.route.name === "detail" && state.route.cameraId) {
            await loadCameraDetailView(state.route.cameraId);
            scheduleCurrentViewRefresh();
            return;
        }
        if (state.route.name === "violations") {
            await loadViolationsView(false);
            scheduleCurrentViewRefresh();
            return;
        }
        if (state.route.name === "settings") {
            await loadSettingsView();
        }
    }

    function renderActiveNav() {
        const routeName = state.route.name === "detail" ? "cameras" : state.route.name;
        els.navLinks.forEach((link) => {
            const isActive = link.getAttribute("data-route") === routeName;
            link.classList.toggle("is-active", isActive);
        });
    }

    function showView(routeName) {
        Object.values(els.views).forEach((view) => {
            if (view) {
                view.hidden = true;
            }
        });
        if (routeName === "detail") {
            els.views.detail.hidden = false;
            return;
        }
        if (els.views[routeName]) {
            els.views[routeName].hidden = false;
        } else {
            els.views.dashboard.hidden = false;
        }
    }

    async function loadDashboardView() {
        try {
            const [overview, cameras, recentViolations, hourly] = await Promise.all([
                fetchJson("/dashboard/overview"),
                fetchJson("/dashboard/cameras"),
                fetchJson("/dashboard/recent-violations?limit=5"),
                fetchJson("/dashboard/stats/hourly"),
            ]);

            state.cameras = Array.isArray(cameras) ? cameras : [];
            els.statTotalToday.textContent = String(overview?.violations_today ?? 0);
            els.statOnlineCameras.textContent = `${overview?.online_cameras ?? 0}/${overview?.total_cameras ?? 0}`;
            els.statAiStatus.textContent = overview?.total_cameras ? "Running" : "Idle";
            renderRecentViolations(els.recentViolations, recentViolations);
            renderTrendChart(hourly);
            renderCameraCards(els.dashboardCameraGrid, state.cameras, { compact: true });
            fillCameraFilter();
        } catch (error) {
            renderTableMessage(els.recentViolations, 4, `Khong tai duoc dashboard: ${error.message}`);
            els.dashboardCameraGrid.innerHTML = renderEmptyState("Khong tai duoc danh sach camera.");
        }
    }

    async function loadCamerasView() {
        try {
            const cameras = await fetchJson("/cameras");
            state.cameras = Array.isArray(cameras) ? cameras : [];
            renderCameraCards(els.cameraGrid, state.cameras, { compact: false });
            fillCameraFilter();
        } catch (error) {
            els.cameraGrid.innerHTML = renderEmptyState(`Khong tai duoc camera: ${escapeHtml(error.message)}`);
        }
    }

    async function loadCameraDetailView(cameraId) {
        try {
            const [camera, liveView, zones, streamStatus, recentViolations] = await Promise.all([
                fetchJson(`/cameras/${cameraId}`),
                fetchJson(`/cameras/${cameraId}/live-view`).catch(() => ({})),
                fetchJson(`/cameras/${cameraId}/zones`).catch(() => ([])),
                fetchJson(`/streams/${cameraId}`).catch(() => ({})),
                fetchJson(`/violations?camera_id=${cameraId}&limit=10`).catch(() => ([])),
            ]);

            const overlay = normalizeLiveView(liveView);
            state.overlayState = overlay;
            renderCameraDetail(camera, overlay, zones || [], streamStatus || {});
            renderRecentViolations(els.cameraRecentViolations, recentViolations, true);
            openDetailRealtime(cameraId);
        } catch (error) {
            els.cameraTitle.textContent = `Camera ${cameraId}`;
            els.cameraSubtitle.textContent = error.message;
            setViewerState(false, "Khong tai duoc camera.");
            renderTableMessage(els.cameraRecentViolations, 4, "Khong tai duoc recent violations.");
        }
    }

    async function loadViolationsView(resetPage) {
        try {
            await ensureCameraIndex();
            fillCameraFilter();

            if (resetPage && els.filterDate) {
                state.route.search.delete("page");
            }

            hydrateViolationFilters();
            const query = buildViolationQuery();
            const violations = await fetchJson(`/violations?${query.toString()}`);
            renderViolations(violations);
        } catch (error) {
            renderTableMessage(els.violationsList, 7, `Khong tai duoc violations: ${error.message}`);
        }
    }

    async function loadSettingsView() {
        els.settingsCurrentPath.textContent = `${normalizePath(window.location.pathname)}${window.location.search}`;
        els.settingsApiRoot.textContent = apiRoot;
        els.settingsRefreshInterval.textContent = `${Math.round(refreshMs / 1000)}s`;

        try {
            const settings = await fetchJson("/settings/system");
            els.settingsApiRoot.textContent = `${apiRoot} | MQTT ${settings.mqtt_host || "-"}`;
        } catch (error) {
            els.settingsApiRoot.textContent = `${apiRoot} | settings error`;
        }
    }

    async function ensureCameraIndex() {
        if (state.cameras.length > 0) {
            return state.cameras;
        }
        const cameras = await fetchJson("/cameras");
        state.cameras = Array.isArray(cameras) ? cameras : [];
        return state.cameras;
    }

    function renderCameraCards(target, cameras, options) {
        if (!target) {
            return;
        }

        if (!Array.isArray(cameras) || cameras.length === 0) {
            target.innerHTML = renderEmptyState("Chua co camera nao.");
            return;
        }

        const compact = Boolean(options?.compact);
        target.innerHTML = cameras.map((camera) => renderCameraCard(camera, compact)).join("");
    }

    function renderCameraCard(camera, compact) {
        const cameraId = Number(camera.camera_id);
        const cameraName = escapeHtml(camera.camera_name || camera.tb_device_name || `Camera ${cameraId}`);
        const subtitle = escapeHtml(camera.location || camera.ip_address || "Chua co vi tri");
        const path = buildCameraPath(camera);
        const status = getCameraStatus(camera);
        const previewUrl = `${apiRoot}/cameras/${cameraId}/snapshot?ts=${Date.now()}`;
        const preview = camera.stream_connected
            ? `<img src="${previewUrl}" alt="${cameraName}" loading="lazy">`
            : `<div class="camera-card__placeholder">Khong co preview</div>`;

        return `
            <article class="camera-card panel">
                <div class="camera-card__header">
                    <div>
                        <h3>${cameraName}</h3>
                        <p class="muted">${subtitle}</p>
                    </div>
                    <div class="camera-card__badges">
                        ${renderStatusBadge(status)}
                    </div>
                </div>
                <a class="camera-card__preview" href="${path}" data-camera-path="${path}">
                    ${preview}
                </a>
                <div class="camera-card__meta">
                    <span>IP <strong>${escapeHtml(camera.ip_address || "-")}</strong></span>
                    <span>Den <strong>${escapeHtml(camera.light_mode || camera.light_state || "unknown")}</strong></span>
                    <span>Stream <strong>${camera.stream_connected ? "connected" : (camera.stream_running ? "retrying" : "stopped")}</strong></span>
                    <span>Violations <strong>${Number(camera.violations_today || 0)}</strong></span>
                    <span>Last seen <strong>${formatDate(camera.last_seen_at)}</strong></span>
                </div>
                <div class="camera-card__actions">
                    <button class="button button--secondary" type="button" data-camera-path="${path}">Xem chi tiet</button>
                    ${compact ? "" : `<button class="button button--ghost" type="button" data-reload-camera="${cameraId}">Reload</button>`}
                </div>
            </article>
        `;
    }

    function renderStatusBadge(status) {
        return `<span class="badge ${status.className}">${escapeHtml(status.label)}</span>`;
    }

    function getCameraStatus(camera) {
        if (camera.stream_connected) {
            return { label: "Online", className: "badge--good" };
        }
        if (camera.online && camera.stream_running) {
            return { label: "Stream Error", className: "badge--bad" };
        }
        if (camera.online) {
            return { label: "Unknown", className: "badge--warn" };
        }
        return { label: "Offline", className: "badge--dim" };
    }

    function renderCameraDetail(camera, liveView, zones, streamStatus) {
        const cameraId = Number(camera.camera_id);
        const cameraName = camera.camera_name || camera.tb_device_name || `Camera ${cameraId}`;
        els.cameraTitle.textContent = cameraName;
        els.cameraSubtitle.textContent = `${camera.location || "Chua cau hinh"} | ${camera.mac_address || "No MAC"}`;
        document.title = `${cameraName} | ${config.appTitle || "Camera AI"}`;

        const onlineStatus = camera.online ? { text: "online", className: "badge--good" } : { text: "offline", className: "badge--dim" };
        const streamStatusBadge = camera.stream_connected
            ? { text: "stream connected", className: "badge--good" }
            : (camera.stream_running ? { text: "stream retrying", className: "badge--warn" } : { text: "stream stopped", className: "badge--bad" });

        setBadge(els.onlineBadge, onlineStatus.text, onlineStatus.className);
        setBadge(els.streamBadge, streamStatusBadge.text, streamStatusBadge.className);

        els.lightState.textContent = liveView.traffic_light_state || camera.light_mode || "unknown";
        els.detectionCount.textContent = String(liveView.detection_count ?? 0);
        els.frameSize.textContent = liveView.frame_width ? `${liveView.frame_width} x ${liveView.frame_height}` : "-";
        els.capturedAt.textContent = formatDate(liveView.captured_at || liveView.updated_at);
        els.cameraIp.textContent = camera.ip_address || "-";
        els.cameraStreamUrl.textContent = camera.stream_url || "-";
        els.workerState.textContent = streamStatus.running ? (streamStatus.connected ? "connected" : "running") : "stopped";
        els.retryCount.textContent = String(streamStatus.retry_count || camera.stream_retry_count || 0);
        els.lastFrameAt.textContent = formatDate(streamStatus.last_frame_at || camera.stream_last_frame_at);
        els.lastError.textContent = streamStatus.last_error || camera.stream_last_error || "-";

        renderZones(zones);
        renderStream(cameraId, camera, streamStatus);
        drawOverlay(liveView);
    }

    function renderZones(zones) {
        const list = Array.isArray(zones) ? zones : [];
        els.zoneCount.textContent = String(list.length);

        if (list.length === 0) {
            els.zoneLegend.innerHTML = `<p class="muted">Chua co zone nao.</p>`;
            return;
        }

        els.zoneLegend.innerHTML = list.map((zone) => {
            const zoneType = normalizeZoneType(zone.zone_type);
            return `
                <div class="zone-legend__item">
                    <span class="zone-legend__dot zone-legend__dot--${zoneType}"></span>
                    <span>${escapeHtml(zone.zone_name || zone.zone_type || "zone")}</span>
                    <code>${escapeHtml(zoneType)}</code>
                    <span class="muted">${zone.x}, ${zone.y}, ${zone.width}, ${zone.height}</span>
                </div>
            `;
        }).join("");
    }

    function renderStream(cameraId, camera, streamStatus) {
        const canShow = Boolean(camera.stream_running || streamStatus.running || camera.stream_connected || streamStatus.connected);
        if (canShow) {
            const streamUrl = `${apiRoot}/cameras/${cameraId}/stream`;
            if (els.streamImage.getAttribute("src") !== streamUrl) {
                els.streamImage.src = streamUrl;
            }
            setViewerState(true, "");
            return;
        }

        els.streamImage.removeAttribute("src");
        const warning = streamStatus.last_error || camera.stream_last_error || "Chua co ket noi camera.";
        setViewerState(false, warning);
    }

    function setViewerState(hasStream, message) {
        els.viewerEmpty.hidden = hasStream;
        els.streamWarning.hidden = !message;
        els.streamWarning.textContent = message || "";
        if (!hasStream) {
            els.viewerEmpty.textContent = message || "Chua co ket noi Camera.";
        }
    }

    function drawOverlay(liveView) {
        state.overlayState = liveView || null;
        const canvas = els.overlayCanvas;
        const image = els.streamImage;
        if (!canvas || !image) {
            return;
        }

        canvas.style.display = state.overlayEnabled ? "block" : "none";
        if (!state.overlayEnabled) {
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }

        const width = image.clientWidth || image.naturalWidth || liveView?.frame_width || 1280;
        const height = image.clientHeight || image.naturalHeight || liveView?.frame_height || 720;
        if (!width || !height) {
            return;
        }

        canvas.width = width;
        canvas.height = height;

        const frameWidth = Number(liveView?.frame_width || image.naturalWidth || width);
        const frameHeight = Number(liveView?.frame_height || image.naturalHeight || height);
        const scaleX = width / frameWidth;
        const scaleY = height / frameHeight;
        const ctx = canvas.getContext("2d");

        ctx.clearRect(0, 0, width, height);
        ctx.lineWidth = 2;
        ctx.font = "12px Segoe UI, sans-serif";

        (liveView?.detections || []).forEach((item) => {
            const bbox = Array.isArray(item.bbox) ? item.bbox : null;
            if (!bbox || bbox.length !== 4) {
                return;
            }
            const x = bbox[0] * scaleX;
            const y = bbox[1] * scaleY;
            const w = (bbox[2] - bbox[0]) * scaleX;
            const h = (bbox[3] - bbox[1]) * scaleY;
            ctx.strokeStyle = item.is_violation ? "#f85149" : "#58a6ff";
            ctx.fillStyle = item.is_violation ? "rgba(248,81,73,0.16)" : "rgba(88,166,255,0.14)";
            ctx.strokeRect(x, y, w, h);
            ctx.fillRect(x, y, w, h);

            const label = `${item.plate_text || "plate"} ${Math.round((item.confidence || 0) * 100)}%`;
            const labelWidth = ctx.measureText(label).width + 10;
            ctx.fillStyle = "#0d1117";
            ctx.fillRect(x, Math.max(0, y - 20), labelWidth, 18);
            ctx.fillStyle = "#ffffff";
            ctx.fillText(label, x + 5, Math.max(12, y - 7));
        });
    }

    function renderRecentViolations(target, violations, detailMode) {
        if (!Array.isArray(violations) || violations.length === 0) {
            renderTableMessage(target, 4, "Chua co vi pham.");
            return;
        }

        target.innerHTML = violations.map((item) => `
            <tr>
                <td>${formatDate(item.timestamp)}</td>
                <td>${escapeHtml(item.license_plate || "-")}</td>
                <td>${detailMode ? (item.confidence ? `${Number(item.confidence).toFixed(2)}` : "-") : escapeHtml(item.camera_name || `Cam ${item.camera_id}`)}</td>
                <td>
                    <button class="button button--ghost" type="button" data-evidence='${escapeAttr(JSON.stringify(item))}'>Xem</button>
                </td>
            </tr>
        `).join("");
    }

    function renderViolations(violations) {
        if (!Array.isArray(violations) || violations.length === 0) {
            renderTableMessage(els.violationsList, 7, "Khong co vi pham nao.");
            return;
        }

        els.violationsList.innerHTML = violations.map((item) => `
            <tr>
                <td>#${Number(item.id)}</td>
                <td>
                    <button class="button button--ghost" type="button" data-evidence='${escapeAttr(JSON.stringify(item))}'>Mo</button>
                </td>
                <td>${formatDate(item.timestamp)}</td>
                <td>${escapeHtml(item.camera_name || `Cam ${item.camera_id}`)}</td>
                <td>${escapeHtml(item.license_plate || "-")}</td>
                <td>${escapeHtml(item.violation_type || "red_light")}</td>
                <td>${item.processed ? '<span class="badge badge--good">processed</span>' : '<span class="badge badge--warn">pending</span>'}</td>
            </tr>
        `).join("");
    }

    function renderTrendChart(points) {
        if (!Array.isArray(points) || points.length === 0) {
            els.trendChart.innerHTML = `<p class="muted">Chua co du lieu.</p>`;
            return;
        }

        const max = Math.max(...points.map((item) => Number(item.count || 0)), 1);
        els.trendChart.innerHTML = points.map((item) => {
            const count = Number(item.count || 0);
            const height = Math.max(8, Math.round((count / max) * 160));
            return `
                <div class="trend-slot">
                    <div class="trend-bar" style="height:${height}px" data-value="${count}"></div>
                    <div class="trend-label">${escapeHtml(item.hour || item.label || "--")}</div>
                </div>
            `;
        }).join("");
    }

    function renderTableMessage(target, colspan, message) {
        if (!target) {
            return;
        }
        target.innerHTML = `<tr><td colspan="${colspan}" class="muted text-center">${escapeHtml(message)}</td></tr>`;
    }

    function renderEmptyState(message) {
        return `<div class="empty-state">${escapeHtml(message)}</div>`;
    }

    function openGlobalRealtime() {
        if (state.globalEvents) {
            state.globalEvents.close();
        }

        state.globalEvents = new EventSource(`${apiRoot}/realtime/stream`);
        state.globalEvents.addEventListener("update", () => queueCurrentViewRefresh());
        state.globalEvents.onerror = () => {
            if (state.globalEvents) {
                state.globalEvents.close();
                state.globalEvents = null;
            }
            window.setTimeout(openGlobalRealtime, 3000);
        };
    }

    function openDetailRealtime(cameraId) {
        closeDetailRealtime();
        state.detailEvents = new EventSource(`${apiRoot}/cameras/${cameraId}/live-view/sse`);
        state.detailEvents.onmessage = (event) => {
            try {
                const payload = normalizeLiveView(JSON.parse(event.data));
                state.overlayState = payload;
                updateLiveRuntime(payload);
                drawOverlay(payload);
            } catch (error) {
                console.warn("Invalid detail SSE payload", error);
            }
        };
        state.detailEvents.onerror = () => {
            closeDetailRealtime();
            if (state.route.name === "detail" && state.currentCameraId === cameraId) {
                window.setTimeout(() => openDetailRealtime(cameraId), 3000);
            }
        };
    }

    function closeDetailRealtime() {
        if (state.detailEvents) {
            state.detailEvents.close();
            state.detailEvents = null;
        }
    }

    function updateLiveRuntime(payload) {
        els.lightState.textContent = payload.traffic_light_state || els.lightState.textContent;
        els.detectionCount.textContent = String(payload.detection_count ?? els.detectionCount.textContent ?? 0);
        els.frameSize.textContent = payload.frame_width ? `${payload.frame_width} x ${payload.frame_height}` : els.frameSize.textContent;
        els.capturedAt.textContent = formatDate(payload.captured_at || payload.updated_at);
    }

    function scheduleCurrentViewRefresh() {
        clearRefreshTimer();
        state.refreshTimer = window.setTimeout(handleRoute, refreshMs);
    }

    function clearRefreshTimer() {
        if (state.refreshTimer) {
            window.clearTimeout(state.refreshTimer);
            state.refreshTimer = null;
        }
    }

    function queueCurrentViewRefresh() {
        if (state.route.name === "detail") {
            return;
        }
        if (state.refreshQueued) {
            return;
        }
        state.refreshQueued = true;
        window.setTimeout(async () => {
            state.refreshQueued = false;
            await handleRoute();
        }, 600);
    }

    function hydrateViolationFilters() {
        els.filterPlate.value = state.route.search.get("license_plate") || "";
        els.filterCamera.value = state.route.search.get("camera_id") || "";
        els.filterDate.value = state.route.search.get("date_from") || "";
    }

    function fillCameraFilter() {
        if (!els.filterCamera) {
            return;
        }

        const selected = state.route.search.get("camera_id") || els.filterCamera.value;
        const options = ['<option value="">Tat ca</option>'].concat(
            state.cameras.map((camera) => {
                const id = Number(camera.camera_id);
                const name = escapeHtml(camera.camera_name || camera.tb_device_name || `Camera ${id}`);
                return `<option value="${id}">${name}</option>`;
            })
        );
        els.filterCamera.innerHTML = options.join("");
        if (selected) {
            els.filterCamera.value = selected;
        }
    }

    function buildViolationQuery() {
        const query = new URLSearchParams();
        query.set("limit", "20");

        const plate = els.filterPlate.value.trim();
        const cameraId = els.filterCamera.value.trim();
        const date = els.filterDate.value.trim();

        if (plate) {
            query.set("license_plate", plate);
        }
        if (cameraId) {
            query.set("camera_id", cameraId);
        }
        if (date) {
            query.set("date_from", date);
            query.set("date_to", date);
        }

        return query;
    }

    function applyViolationFilters() {
        const query = buildViolationQuery();
        navigate(`/violations?${query.toString()}`);
    }

    async function reloadCurrentCameraStream() {
        if (!state.currentCameraId) {
            return;
        }
        await reloadCameraStream(state.currentCameraId);
        await loadCameraDetailView(state.currentCameraId);
    }

    async function reloadCameraStream(cameraId) {
        try {
            await fetchJson(`/streams/${cameraId}/start`, { method: "POST" });
            queueCurrentViewRefresh();
        } catch (error) {
            console.warn("Reload stream failed", error);
        }
    }

    function toggleOverlay() {
        state.overlayEnabled = !state.overlayEnabled;
        els.toggleOverlayBtn.textContent = `Overlay: ${state.overlayEnabled ? "ON" : "OFF"}`;
        drawOverlay(state.overlayState);
    }

    function syncStaticSettings() {
        const serverLabel = apiBase || window.location.origin;
        if (els.serverIp) {
            els.serverIp.textContent = serverLabel;
        }
        if (els.apiHealthLink) {
            els.apiHealthLink.href = apiBase ? `${apiBase}/health` : "/health";
        }
        if (els.toggleOverlayBtn) {
            els.toggleOverlayBtn.textContent = "Overlay: ON";
        }
    }

    function setBadge(node, text, className) {
        if (!node) {
            return;
        }
        node.textContent = text;
        node.className = `badge ${className}`;
    }

    function buildCameraPath(camera) {
        const cameraId = Number(camera.camera_id);
        const slug = slugify(camera.camera_name || camera.tb_device_name || camera.location || `camera-${cameraId}`);
        return `/cameras/${cameraId}-${slug}`;
    }

    function normalizeLiveView(payload) {
        if (!payload || typeof payload !== "object") {
            return {};
        }
        if (payload.overlay && typeof payload.overlay === "object") {
            return payload.overlay;
        }
        return payload;
    }

    function slugify(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "") || "camera";
    }

    function normalizeZoneType(zoneType) {
        const raw = String(zoneType || "").toLowerCase();
        if (raw === "stop_line") {
            return "stop";
        }
        if (raw === "violation_zone") {
            return "violation";
        }
        if (raw === "roi") {
            return "roi";
        }
        return "detect";
    }

    function openEvidenceModal(item) {
        if (!els.evidenceModal) {
            return;
        }
        els.modalFullImage.src = item.full_image_url || "";
        els.modalPlateImage.src = item.cropped_plate_url || "";
        els.modalDetails.innerHTML = [
            kv("ID", item.id || "-"),
            kv("Camera", item.camera_name || `Cam ${item.camera_id || "-"}`),
            kv("Bien so", item.license_plate || "-"),
            kv("Loai", item.violation_type || "red_light"),
            kv("Thoi gian", formatDate(item.timestamp)),
            kv("Confidence", item.confidence ? Number(item.confidence).toFixed(2) : "-"),
        ].join("");
        els.evidenceModal.hidden = false;
    }

    function closeEvidenceModal() {
        if (els.evidenceModal) {
            els.evidenceModal.hidden = true;
        }
    }

    function kv(label, value) {
        return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value || "-"))}</dd></div>`;
    }

    async function fetchJson(path, options) {
        const response = await fetch(`${apiRoot}${path}`, {
            headers: { Accept: "application/json" },
            ...options,
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || `HTTP ${response.status}`);
        }

        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            return {};
        }
        return response.json();
    }

    function formatDate(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return date.toLocaleString("vi-VN");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function escapeAttr(value) {
        return escapeHtml(value);
    }
})();
