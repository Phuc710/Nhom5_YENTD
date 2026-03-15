/**
 * zone-editor.js — Drag/Resize/Draw detection zones
 * Phủ lên stream image của ESP32-S3-CAM.
 *
 * API:
 *   const ze = new ZoneEditor(containerEl, streamImgEl);
 *   ze.loadZones(zonesArray);    // load từ API
 *   ze.getZones();               // lấy zones hiện tại
 *   ze.on('change', cb);         // callback khi zone thay đổi
 */

class ZoneEditor {
    constructor(container, streamImg) {
        this._container = container;
        this._img = streamImg;
        this._zones = [];
        this._selected = null;
        this._drawing = false;
        this._drawStart = null;
        this._dragState = null;
        this._listeners = {};
        this._zoneCount = 0;

        this._initOverlay();
        this._bindEvents();

        // Re-layout khi ảnh resize
        const ro = new ResizeObserver(() => this._redraw());
        ro.observe(streamImg);
    }

    // ---- Init overlay canvas --------------------------------
    _initOverlay() {
        this._overlay = document.createElement('div');
        this._overlay.className = 'zone-editor__overlay';
        Object.assign(this._overlay.style, {
            position: 'absolute', inset: '0',
            pointerEvents: 'none',
            zIndex: 10,
        });
        this._container.style.position = 'relative';
        this._container.appendChild(this._overlay);
    }

    // ---- Event binding (draw on image) ----------------------
    _bindEvents() {
        const img = this._img;

        img.addEventListener('mousedown', e => {
            if (this._dragState) return;
            const r = img.getBoundingClientRect();
            this._drawing = true;
            this._drawStart = { x: e.clientX - r.left, y: e.clientY - r.top };
            this._tmpEl = this._createTempBox();
            e.preventDefault();
        });

        window.addEventListener('mousemove', e => {
            if (!this._drawing || !this._drawStart) return;
            const r = this._img.getBoundingClientRect();
            const cx = Math.max(0, Math.min(e.clientX - r.left, r.width));
            const cy = Math.max(0, Math.min(e.clientY - r.top, r.height));
            const x = Math.min(cx, this._drawStart.x);
            const y = Math.min(cy, this._drawStart.y);
            const w = Math.abs(cx - this._drawStart.x);
            const h = Math.abs(cy - this._drawStart.y);
            if (this._tmpEl) {
                Object.assign(this._tmpEl.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
            }
        });

        window.addEventListener('mouseup', e => {
            if (!this._drawing) return;
            this._drawing = false;
            const r = this._img.getBoundingClientRect();
            const cx = Math.max(0, Math.min(e.clientX - r.left, r.width));
            const cy = Math.max(0, Math.min(e.clientY - r.top, r.height));
            const pw = r.width; const ph = r.height;

            const xPx = Math.min(cx, this._drawStart.x);
            const yPx = Math.min(cy, this._drawStart.y);
            const wPx = Math.abs(cx - this._drawStart.x);
            const hPx = Math.abs(cy - this._drawStart.y);

            if (this._tmpEl) {
                this._tmpEl.remove();
                this._tmpEl = null;
            }

            if (wPx < 10 || hPx < 10) return;

            this._zoneCount++;
            const zone = {
                id: 'z_' + Date.now(),
                zone_name: `zone-${this._zoneCount}`,
                zone_type: this._currentType || 'detection',
                // Lưu normalized để scale
                xn: xPx / pw,
                yn: yPx / ph,
                wn: wPx / pw,
                hn: hPx / ph,
            };
            this._zones.push(zone);
            this._renderBox(zone);
            this._select(zone.id);
            this._emit('change', this.getZones());
        });
    }

    _createTempBox() {
        const el = document.createElement('div');
        Object.assign(el.style, {
            position: 'absolute',
            border: '2px dashed #22C55E',
            background: 'rgba(34,197,94,.1)',
            pointerEvents: 'none',
            zIndex: 9,
        });
        this._container.appendChild(el);
        return el;
    }

    // ---- Render zone box ------------------------------------
    _renderBox(zone) {
        const el = document.createElement('div');
        el.className = `zone-box zone-box--${zone.zone_type.replace(/_/g, '-')}`;
        el.dataset.id = zone.id;

        this._updateBoxEl(zone, el);

        // Label (editable name)
        const label = document.createElement('div');
        label.className = 'zone-box__label';
        label.textContent = zone.zone_name;
        label.contentEditable = 'true';
        label.spellcheck = false;
        label.addEventListener('input', () => {
            zone.zone_name = label.textContent.trim();
            this._emit('change', this.getZones());
        });
        label.addEventListener('mousedown', e => e.stopPropagation());
        el.appendChild(label);

        // Delete button
        const del = document.createElement('button');
        del.className = 'zone-box__delete';
        del.innerHTML = '&times;';
        del.title = 'Xóa zone';
        del.addEventListener('mousedown', e => { e.stopPropagation(); this._removeZone(zone.id); });
        el.appendChild(del);

        // Resize handles
        ['tl', 'tr', 'bl', 'br'].forEach(pos => {
            const h = document.createElement('div');
            h.className = `zone-box__handle zone-box__handle--${pos}`;
            h.addEventListener('mousedown', e => {
                e.stopPropagation();
                this._startResize(zone, pos, e);
            });
            el.appendChild(h);
        });

        // Drag move
        el.addEventListener('mousedown', e => {
            if (e.target.classList.contains('zone-box__handle')) return;
            if (e.target.classList.contains('zone-box__delete')) return;
            this._select(zone.id);
            this._startMove(zone, e);
        });

        this._overlay.appendChild(el);
    }

    _startMove(zone, e) {
        const startX = e.clientX, startY = e.clientY;
        const oxn = zone.xn, oyn = zone.yn;
        const r = this._img.getBoundingClientRect();

        const onMove = ev => {
            const dxn = (ev.clientX - startX) / r.width;
            const dyn = (ev.clientY - startY) / r.height;
            zone.xn = Math.max(0, Math.min(oxn + dxn, 1 - zone.wn));
            zone.yn = Math.max(0, Math.min(oyn + dyn, 1 - zone.hn));
            this._updateBoxEl(zone);
            this._emit('change', this.getZones());
        };
        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }

    _startResize(zone, handle, e) {
        e.preventDefault();
        const startX = e.clientX, startY = e.clientY;
        const oxn = zone.xn, oyn = zone.yn, own = zone.wn, ohn = zone.hn;
        const r = this._img.getBoundingClientRect();

        const onMove = ev => {
            const dxn = (ev.clientX - startX) / r.width;
            const dyn = (ev.clientY - startY) / r.height;

            if (handle === 'br') {
                zone.wn = Math.max(0.01, own + dxn);
                zone.hn = Math.max(0.01, ohn + dyn);
            }
            else if (handle === 'bl') {
                const nx = Math.max(0, oxn + dxn);
                zone.wn = Math.max(0.01, own + (oxn - nx));
                zone.xn = nx;
                zone.hn = Math.max(0.01, ohn + dyn);
            }
            else if (handle === 'tr') {
                zone.wn = Math.max(0.01, own + dxn);
                const ny = Math.max(0, oyn + dyn);
                zone.hn = Math.max(0.01, ohn + (oyn - ny));
                zone.yn = ny;
            }
            else if (handle === 'tl') {
                const nx = Math.max(0, oxn + dxn);
                zone.wn = Math.max(0.01, own + (oxn - nx));
                zone.xn = nx;
                const ny = Math.max(0, oyn + dyn);
                zone.hn = Math.max(0.01, ohn + (oyn - ny));
                zone.yn = ny;
            }
            this._updateBoxEl(zone);
            this._emit('change', this.getZones());
        };
        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }

    _updateBoxEl(zone, el = null) {
        if (!el) el = this._overlay.querySelector(`[data-id="${zone.id}"]`);
        if (!el) return;
        const r = this._img.getBoundingClientRect();
        Object.assign(el.style, {
            left: (zone.xn * r.width) + 'px',
            top: (zone.yn * r.height) + 'px',
            width: (zone.wn * r.width) + 'px',
            height: (zone.hn * r.height) + 'px'
        });
        const lbl = el.querySelector('.zone-box__label');
        if (lbl && !lbl.matches(':focus')) lbl.textContent = zone.zone_name;
    }

    _removeZone(id) {
        this._zones = this._zones.filter(z => z.id !== id);
        const el = this._overlay.querySelector(`[data-id="${id}"]`);
        if (el) el.remove();
        if (this._selected === id) this._selected = null;
        this._emit('change', this.getZones());
    }

    _select(id) {
        this._selected = id;
        this._overlay.querySelectorAll('.zone-box').forEach(el => {
            el.classList.toggle('zone-box--selected', el.dataset.id === id);
        });
        const zone = this._zones.find(z => z.id === id);
        this._emit('select', zone || null);
    }

    _redraw() {
        this._zones.forEach(z => this._updateBoxEl(z));
    }

    // ---- Public API -----------------------------------------

    loadZones(apiZones) {
        this._zones = [];
        this._overlay.innerHTML = '';
        const nw = this._img.naturalWidth || 640;
        const nh = this._img.naturalHeight || 480;

        apiZones.forEach((z, i) => {
            this._zones.push({
                id: z.id || 'z_' + i,
                zone_name: z.zone_name || `zone-${i + 1}`,
                zone_type: z.zone_type || 'detection',
                // Chuyển từ pixels sang normalized
                xn: z.x / nw,
                yn: z.y / nh,
                wn: (z.width || z.w) / nw,
                hn: (z.height || z.h) / nh,
            });
            this._zoneCount = Math.max(this._zoneCount, i + 1);
        });
        this._redraw();
        this._zones.forEach(z => this._renderBox(z));
    }

    getZones() {
        const nw = this._img.naturalWidth || 640;
        const nh = this._img.naturalHeight || 480;
        return this._zones.map(z => ({
            zone_name: z.zone_name,
            zone_type: z.zone_type,
            x: Math.round(z.xn * nw),
            y: Math.round(z.yn * nh),
            width: Math.round(z.wn * nw),
            height: Math.round(z.hn * nh),
            active: true,
        }));
    }

    setZoneType(type) { this._currentType = type; }

    clearAll() {
        this._zones = [];
        this._overlay.innerHTML = '';
        this._emit('change', []);
    }

    on(event, cb) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(cb);
        return this;
    }

    _emit(event, data) {
        (this._listeners[event] || []).forEach(cb => cb(data));
    }
}
