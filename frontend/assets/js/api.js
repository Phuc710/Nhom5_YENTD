/**
 * api.js — Fetch wrapper cho Backend API
 * Tất cả request qua đây.
 */

const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_URL)
    || 'http://localhost:8000';

class ApiClient {
    constructor(baseUrl = API_BASE) {
        this.base = baseUrl.replace(/\/$/, '');
    }

    async _request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(this.base + path, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return res.json();
    }

    get(path) { return this._request('GET', path); }
    post(path, body) { return this._request('POST', path, body); }
    put(path, body) { return this._request('PUT', path, body); }
    delete(path) { return this._request('DELETE', path); }
    patch(path, body) { return this._request('PATCH', path, body); }

    // ---- Cameras ----------------------------------------
    getCameras() { return this.get('/api/cameras'); }
    getCamera(id) { return this.get(`/api/cameras/${id}`); }
    updateCamera(id, data) { return this.put(`/api/cameras/${id}`, data); }
    getZones(cameraId) { return this.get(`/api/cameras/${cameraId}/zones`); }
    saveZones(cameraId, zones) { return this.put(`/api/cameras/${cameraId}/zones`, { zones }); }

    // ---- Violations -------------------------------------
    getViolations(params = {}) {
        const qs = new URLSearchParams(Object.fromEntries(
            Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
        )).toString();
        return this.get(`/api/violations${qs ? '?' + qs : ''}`);
    }
    getViolation(id) { return this.get(`/api/violations/${id}`); }
    getRecentViolations(limit = 10) { return this.get(`/api/violations/recent?limit=${limit}`); }
    getSummary() { return this.get('/api/violations/stats/summary'); }
}

// Singleton
const api = new ApiClient();

// ---- Helpers --------------------------------------------
function formatDateVN(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('vi-VN', {
        timeZone: 'Asia/Ho_Chi_Minh',
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false,
    });
}

function plateBadge(plate) {
    if (!plate) return '<span class="badge badge--gray">Không rõ</span>';
    return `<span class="plate">${plate}</span>`;
}

function lightBadge(state) {
    const map = { red: ['badge--red', 'Đèn đỏ'], yellow: ['badge--yellow', 'Đèn vàng'], green: ['badge--green', 'Đèn xanh'] };
    const [cls, label] = map[state] || ['badge--gray', state];
    return `<span class="badge ${cls}">${label}</span>`;
}

function onlineBadge(online) {
    return online
        ? '<span class="badge badge--green">Online</span>'
        : '<span class="badge badge--gray">Offline</span>';
}
