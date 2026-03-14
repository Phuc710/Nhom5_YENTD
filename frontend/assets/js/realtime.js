(function () {
    const hub = window.liveDataHub;
    if (!hub || !window.api) {
        return;
    }

    if (typeof window.EventSource !== 'function') {
        hub.setRealtimeStatus('disabled');
        return;
    }

    let eventSource = null;
    let reconnectDelay = 2000;
    let reconnectTimer = null;

    const clearReconnect = () => {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    };

    const cleanupSource = () => {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    };

    const scheduleReconnect = () => {
        clearReconnect();
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    };

    const handleMessage = (raw) => {
        if (!raw) return;

        try {
            const message = JSON.parse(raw);

            if (message.table) {
                hub.notifyRealtime(message.table);
                return;
            }

            if (Array.isArray(message.resources) && message.resources.length) {
                hub.requestSync({
                    resources: message.resources,
                    reason: `sse:${message.type || 'update'}`,
                });
            }
        } catch (error) {
            console.error('SSE parse error:', error);
        }
    };

    function connect() {
        clearReconnect();
        cleanupSource();
        hub.setRealtimeStatus('connecting');

        eventSource = new EventSource(api.getRealtimeStreamUrl());

        eventSource.addEventListener('ready', () => {
            reconnectDelay = 2000;
            hub.setRealtimeStatus('subscribed');
            hub.requestSync({ reason: 'sse-ready' });
        });

        eventSource.addEventListener('update', (event) => {
            reconnectDelay = 2000;
            hub.setRealtimeStatus('subscribed');
            handleMessage(event.data);
        });

        eventSource.onmessage = (event) => {
            reconnectDelay = 2000;
            hub.setRealtimeStatus('subscribed');
            handleMessage(event.data);
        };

        eventSource.onerror = () => {
            hub.setRealtimeStatus('error');
            cleanupSource();
            scheduleReconnect();
        };
    }

    window.addEventListener('beforeunload', () => {
        clearReconnect();
        cleanupSource();
    });

    connect();
})();
