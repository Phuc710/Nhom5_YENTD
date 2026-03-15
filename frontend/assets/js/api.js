const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_URL) || window.location.origin;

function resolveCameraDisplayName(camera) {
    const id = camera?.camera_id || 0;
    return (
        camera?.camera_name
        || camera?.device_name
        || camera?.project_name
        || camera?.tb_device_name
        || `Camera ${String(id).padStart(3, '0')}`
    );
}

class ApiClient {
    constructor(baseUrl = API_BASE) {
        this.base = baseUrl.replace(/\/$/, '');
        this.controllers = new Map();
    }

    buildUrl(path) {
        return this.base + path;
    }

    async _request(method, path, body = null, requestOptions = {}) {
        const { signal = null, requestKey = null, headers = {} } = requestOptions;
        const controller = !signal && requestKey ? new AbortController() : null;

        if (requestKey && controller) {
            const previous = this.controllers.get(requestKey);
            if (previous) {
                previous.abort();
            }
            this.controllers.set(requestKey, controller);
        }

        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
                ...headers,
            },
            signal: signal || controller?.signal,
        };

        if (body !== null && body !== undefined) {
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(this.base + path, options);
            const raw = await response.text();
            const payload = raw ? this._safeJson(raw) : null;

            if (!response.ok) {
                const detail = (payload && typeof payload === 'object' && payload.detail) || response.statusText;
                throw new Error(detail || `HTTP ${response.status}`);
            }

            if (response.status === 204 || !raw) {
                return null;
            }

            return payload;
        } finally {
            if (requestKey && controller && this.controllers.get(requestKey) === controller) {
                this.controllers.delete(requestKey);
            }
        }
    }

    _safeJson(raw) {
        try {
            return JSON.parse(raw);
        } catch {
            return raw;
        }
    }

    get(path, options) { return this._request('GET', path, null, options); }
    post(path, body, options) { return this._request('POST', path, body, options); }
    put(path, body, options) { return this._request('PUT', path, body, options); }
    delete(path, options) { return this._request('DELETE', path, null, options); }
    async postForm(path, formData, requestOptions = {}) {
        const { signal = null, requestKey = null, headers = {} } = requestOptions;
        const controller = !signal && requestKey ? new AbortController() : null;

        if (requestKey && controller) {
            const previous = this.controllers.get(requestKey);
            if (previous) previous.abort();
            this.controllers.set(requestKey, controller);
        }

        try {
            const response = await fetch(this.base + path, {
                method: 'POST',
                body: formData,
                signal: signal || controller?.signal,
                headers: {
                    Accept: 'application/json',
                    ...headers,
                },
            });
            const raw = await response.text();
            const payload = raw ? this._safeJson(raw) : null;
            if (!response.ok) {
                const detail = (payload && typeof payload === 'object' && payload.detail) || response.statusText;
                throw new Error(detail || `HTTP ${response.status}`);
            }
            return payload;
        } finally {
            if (requestKey && controller && this.controllers.get(requestKey) === controller) {
                this.controllers.delete(requestKey);
            }
        }
    }

    getCameras(options) { return this.get('/api/cameras', options); }
    getCamera(id, options) { return this.get(`/api/cameras/${id}`, options); }
    getCameraLiveView(id, options) { return this.get(`/api/cameras/${id}/live-view`, options); }
    getCameraStreamProxyUrl(id, cacheBust = null) {
        return this.buildUrl(`/api/cameras/${id}/stream${cacheBust ? `?t=${cacheBust}` : ''}`);
    }
    getCameraSnapshotProxyUrl(id, cacheBust = null) {
        return this.buildUrl(`/api/cameras/${id}/snapshot${cacheBust ? `?t=${cacheBust}` : ''}`);
    }
    getRealtimeStreamUrl() {
        return this.buildUrl('/api/realtime/stream');
    }
    updateCamera(id, data, options) { return this.put(`/api/cameras/${id}`, data, options); }
    deleteCamera(id, options) { return this.delete(`/api/cameras/${id}`, options); }
    factoryResetCamera(id, options) { return this.post(`/api/cameras/${id}/factory-reset`, {}, options); }
    rebootCamera(id, options) { return this.post(`/api/cameras/${id}/reboot`, {}, options); }
    startOTACamera(id, url, options) { return this.post(`/api/cameras/${id}/ota`, { url }, options); }
    setTrafficLightState(id, state, options) { return this.post(`/api/cameras/${id}/traffic-light`, { state }, options); }
    updateCameraIotConfig(id, data, options) { return this.put(`/api/cameras/${id}/iot-config`, data, options); }
    getZones(cameraId, options) { return this.get(`/api/cameras/${cameraId}/zones`, options); }
    saveZones(cameraId, zones, options) { return this.put(`/api/cameras/${cameraId}/zones`, { zones }, options); }
    getDashboardOverview(options) { return this.get('/api/dashboard/overview', options); }
    getDashboardCameras(options) { return this.get('/api/dashboard/cameras', options); }
    getDashboardRecentViolations(limit = 10, options) {
        return this.get(`/api/dashboard/recent-violations?limit=${limit}`, options);
    }

    getViolations(params = {}, options) {
        const qs = new URLSearchParams(
            Object.fromEntries(
                Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== '')
            )
        ).toString();
        return this.get(`/api/violations${qs ? '?' + qs : ''}`, options);
    }

    getViolation(id, options) { return this.get(`/api/violations/${id}`, options); }
    getRecentViolations(limit = 10, options) { return this.get(`/api/violations/recent?limit=${limit}`, options); }
}

const api = new ApiClient();

function formatDateVN(iso) {
    if (!iso) return '--';
    return new Date(iso).toLocaleString('vi-VN', {
        timeZone: 'Asia/Ho_Chi_Minh',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });
}

function normalizePlateClient(plate) {
    return String(plate || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}

function plateBadge(plate) {
    if (!plate) return '<span class="badge badge--gray">Không rõ</span>';
    return `<span class="plate">${plate}</span>`;
}

function lightBadge(state) {
    const map = {
        red: ['badge--red', 'Đèn đỏ'],
        yellow: ['badge--yellow', 'Đèn vàng'],
        green: ['badge--green', 'Đèn xanh'],
    };
    const [klass, label] = map[state] || ['badge--gray', state || '--'];
    return `<span class="badge ${klass}">${label}</span>`;
}

function onlineBadge(online) {
    return online
        ? '<span class="badge badge--green">Online</span>'
        : '<span class="badge badge--gray">Offline</span>';
}

function renderCameraCard(camera) {
    const cameraName = resolveCameraDisplayName(camera);
    const streamPreview = camera.stream_url
        ? `<img class="cam-card__thumb" src="${api.getCameraSnapshotProxyUrl(camera.camera_id, Date.now())}" alt="Snapshot camera" loading="lazy" onerror="this.style.display='none'">`
        : '<div class="cam-card__no-stream">Chưa có luồng</div>';

    return `
        <article class="cam-card">
            <a href="/camera/${camera.camera_id}" class="cam-card__preview">
                ${streamPreview}
                <span class="cam-card__status">
                    <span class="status-dot status-dot--${camera.online ? 'online' : 'offline'}"></span>
                    ${camera.online ? 'Online' : 'Offline'}
                </span>
            </a>
            <div class="cam-card__body">
                <div class="cam-card__name">${cameraName}</div>
                <div class="cam-card__loc">${camera.location || 'Chua co vi tri'}</div>
                <div class="cam-card__stats">
                    <span class="cam-card__stat"><strong>${camera.violations_today ?? 0}</strong> hôm nay</span>
                    <span class="cam-card__stat">${camera.fw_version ? `fw ${camera.fw_version}` : 'Chưa có firmware'}</span>
                </div>
                <div class="cam-card__lastseen">Lần cuối: ${camera.last_seen_at ? formatDateVN(camera.last_seen_at) : '--'}</div>
                <div class="inline-actions" style="margin-top:12px;">
                    <a href="/camera/${camera.camera_id}" class="btn btn--primary btn--sm">Chi tiet</a>
                    <a href="/violations?camera_id=${camera.camera_id}" class="btn btn--outline btn--sm">Vi pham</a>
                </div>
            </div>
        </article>
    `;
}

function renderViolationDetail(violation, options = {}) {
    const setText = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value ?? '--';
    };

    const plate = violation.license_plate || 'Chưa rõ';

    if (document.getElementById('dPlateDisplay')) {
        document.getElementById('dPlateDisplay').textContent = plate;
    }
    if (document.getElementById('dConf')) {
        document.getElementById('dConf').textContent =
            violation.confidence ? `Confidence: ${(violation.confidence * 100).toFixed(1)}%` : '';
    }

    setText('dTitle', `Vi pham #${violation.id}`);
    setText('dSubtitle', `${violation.camera_name || violation.camera_id} · ${formatDateVN(violation.timestamp)}`);
    if (document.getElementById('dPlate')) {
        document.getElementById('dPlate').innerHTML = plateBadge(violation.license_plate);
    }
    if (document.getElementById('dLight')) {
        document.getElementById('dLight').innerHTML = lightBadge(violation.traffic_light_state);
    }
    setText('dType', violation.violation_type || 'red_light');
    setText('dTime', formatDateVN(violation.timestamp));
    setText('dCamera', `Cam #${violation.camera_id}`);
    setText('dLocation', violation.location || '--');
    setText('dConfidence', violation.confidence ? `${(violation.confidence * 100).toFixed(2)}%` : '--');
    setText(
        'dVote',
        violation.vote_count && violation.total_frames
            ? `${violation.vote_count}/${violation.total_frames} (${Number(violation.vote_percent || 0).toFixed(1)}%)`
            : '--'
    );
    setText(
        'dQuality',
        violation.image_quality_score ? `${Number(violation.image_quality_score).toFixed(1)}/100` : '--'
    );
    setText('dProc', violation.processing_time_ms ? `${violation.processing_time_ms}ms` : '--');
    setText('dCamName', violation.camera_name || '--');
    setText('dCamLoc', violation.location || '--');

    const cameraLink = document.getElementById('dCameraLink');
    if (cameraLink) {
        cameraLink.href = `/camera.php?id=${violation.camera_id}`;
    }

    const mapLink = document.getElementById('dMap');
    if (mapLink && violation.latitude && violation.longitude) {
        mapLink.href = `https://www.google.com/maps?q=${violation.latitude},${violation.longitude}`;
    }

    const fullImg = document.getElementById('dFullImg');
    if (fullImg) {
        fullImg.src = violation.stop_line_snapshot_url || violation.full_image_url || '';
    }

    const fullImgLink = document.getElementById('dFullImgLink');
    if (fullImgLink) {
        fullImgLink.href = violation.stop_line_snapshot_url || violation.full_image_url || '#';
    }

    if (document.getElementById('dCropImg')) {
        document.getElementById('dCropImg').src = violation.cropped_plate_url || violation.full_image_url || '';
    }

    if (document.getElementById('dVehicleImg')) {
        document.getElementById('dVehicleImg').src = violation.cropped_vehicle_url || violation.full_image_url || '';
    }

    if (
        !options.disableBbox
        && fullImg
        && violation.bbox_x != null
        && violation.bbox_y != null
        && violation.bbox_w
        && violation.bbox_h
    ) {
        const injectBbox = () => {
            const wrap = document.getElementById('imgWrap');
            if (!wrap) return;
            wrap.querySelectorAll('.violation-bbox').forEach((node) => node.remove());
            const scaleX = fullImg.clientWidth / (fullImg.naturalWidth || fullImg.clientWidth);
            const scaleY = fullImg.clientHeight / (fullImg.naturalHeight || fullImg.clientHeight);
            const box = document.createElement('div');
            box.className = 'violation-bbox';
            Object.assign(box.style, {
                left: `${violation.bbox_x * scaleX}px`,
                top: `${violation.bbox_y * scaleY}px`,
                width: `${violation.bbox_w * scaleX}px`,
                height: `${violation.bbox_h * scaleY}px`,
            });
            const label = document.createElement('div');
            label.className = 'violation-bbox__label';
            label.textContent = plate;
            box.appendChild(label);
            wrap.appendChild(box);
        };

        if (fullImg.complete && fullImg.naturalWidth) {
            injectBbox();
        } else {
            fullImg.addEventListener('load', injectBbox, { once: true });
        }
    }
}
