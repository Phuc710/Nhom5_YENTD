class RealtimeService {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.eventSource = null;
        this.subscribers = new Set();
        this.reconnectTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectDelay = 15000;
    }

    get streamUrl() {
        return `${this.baseUrl}/api/realtime/stream`;
    }

    connect() {
        if (!this.baseUrl) {
            return;
        }

        if (this.eventSource && this.eventSource.readyState !== EventSource.CLOSED) {
            return;
        }

        this.disconnect(false);
        this.eventSource = new EventSource(this.streamUrl);

        this.eventSource.onopen = () => {
            this.reconnectAttempts = 0;
            this._notify({ type: 'status', connected: true });
        };

        this.eventSource.addEventListener('update', (event) => {
            try {
                this._notify({ type: 'message', data: JSON.parse(event.data) });
            } catch (error) {
                console.warn('Malformed realtime event:', error);
            }
        });

        this.eventSource.onerror = () => {
            this._notify({ type: 'status', connected: false });
            this.disconnect(false);
            this._scheduleReconnect();
        };
    }

    disconnect(clearSubscribers = false) {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (clearSubscribers) {
            this.subscribers.clear();
        }
    }

    subscribe(callback) {
        this.subscribers.add(callback);
        this.connect();
        return () => this.subscribers.delete(callback);
    }

    _scheduleReconnect() {
        if (this.reconnectTimer || this.subscribers.size === 0) {
            return;
        }

        this.reconnectAttempts += 1;
        const delay = Math.min(1000 * this.reconnectAttempts, this.maxReconnectDelay);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, delay);
    }

    _notify(payload) {
        this.subscribers.forEach((callback) => {
            try {
                callback(payload);
            } catch (error) {
                console.error('Realtime subscriber failed:', error);
            }
        });
    }
}

const realtimeService = new RealtimeService(window.APP_CONFIG?.API_URL || '');
export default realtimeService;
