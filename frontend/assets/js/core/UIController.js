/**
 * UIController - Lớp cơ sở cho việc quản lý UI Dashboard
 */
class UIController {
    constructor() {
        this.toasts = [];
    }

    /**
     * Shortcut to set text content safely
     */
    setText(id, value, fallback = '--') {
        const el = document.getElementById(id);
        if (el) el.textContent = value ?? fallback;
    }

    /**
     * Shortcut to set HTML content
     */
    setHtml(id, html) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    /**
     * Update status pill classes
     */
    updateStatusPill(id, isOnline) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.toggle('status-pill--online', !!isOnline);
        el.classList.toggle('status-pill--offline', !isOnline);
    }

    /**
     * Hiển thị thông báo (Chuẩn Grok UI)
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container') || this._createToastContainer();
        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.textContent = message;

        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    _createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed; bottom:24px; right:24px; display:flex; flex-direction:column; gap:8px; z-index:9999;';
        document.body.appendChild(container);
        return container;
    }
}

export default UIController;
