/**
 * UI Utilities for Grok UI
 */
const ui = {
    toastContainer: null,

    _initToast() {
        if (this.toastContainer) return;
        this.toastContainer = document.createElement('div');
        this.toastContainer.className = 'toast-container';
        document.body.appendChild(this.toastContainer);
    },

    toast(message, type = 'info', duration = 4000) {
        this._initToast();
        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;

        const icon = type === 'success' ? '✅' : (type === 'error' ? '❌' : 'ℹ️');
        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;

        this.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
};

window.ui = ui;
