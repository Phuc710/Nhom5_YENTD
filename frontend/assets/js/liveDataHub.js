/**
 * Smart Long Polling & Real-time Sync Engine
 * Handles throttled polling based on tab visibility and error management.
 */
class LiveDataHub {
    constructor() {
        this.registry = new Map();
        this.isActive = !document.hidden;
        this.initVisibilityListener();
    }

    initVisibilityListener() {
        document.addEventListener('visibilitychange', () => {
            this.isActive = !document.hidden;
            console.log(`[LiveDataHub] Tab activity changed: ${this.isActive ? 'Active' : 'Background'}`);
            this.restartAll();
        });
    }

    /**
     * Register a resource for polling
     * @param {Object} options 
     * @param {string} options.id - Unique ID for this poll task
     * @param {string[]} options.resources - Resource types (e.g. ['cameras', 'violations'])
     * @param {number} options.intervalVisible - Ms for active tab (min 1000)
     * @param {number} options.intervalHidden - Ms for background tab (min 5000)
     * @param {Function} options.run - The async function that performs the request
     * @param {Function} options.onData - Callback on success
     * @param {Function} options.onError - Callback on error
     */
    register(options) {
        if (this.registry.has(options.id)) {
            this.unregister(options.id);
        }

        const task = {
            ...options,
            lastRun: 0,
            timer: null,
            consecutiveErrors: 0,
            isPolling: false
        };

        this.registry.set(options.id, task);
        this.schedule(task);
        return () => this.unregister(options.id);
    }

    unregister(id) {
        const task = this.registry.get(id);
        if (task) {
            if (task.timer) clearTimeout(task.timer);
            this.registry.delete(id);
        }
    }

    schedule(task) {
        if (task.timer) clearTimeout(task.timer);

        const baseInterval = this.isActive ? task.intervalVisible : task.intervalHidden;
        const backoff = Math.min(task.consecutiveErrors * 5000, 60000); // Max 1 min backoff
        const nextInterval = baseInterval + backoff;

        task.timer = setTimeout(() => this.execute(task), nextInterval);
    }

    async execute(task) {
        if (task.isPolling) return;
        task.isPolling = true;

        try {
            const data = await task.run();
            task.consecutiveErrors = 0;
            if (task.onData) task.onData(data);
        } catch (err) {
            task.consecutiveErrors++;
            console.error(`[LiveDataHub] Error in task ${task.id}:`, err);
            if (task.onError) task.onError(err);
        } finally {
            task.isPolling = false;
            task.lastRun = Date.now();
            if (this.registry.has(task.id)) {
                this.schedule(task);
            }
        }
    }

    restartAll() {
        for (const task of this.registry.values()) {
            if (task.timer) clearTimeout(task.timer);
            const now = Date.now();
            const elapsed = now - task.lastRun;
            const interval = this.isActive ? task.intervalVisible : task.intervalHidden;

            // If we've been idle longer than the current interval, run immediately
            const delay = Math.max(0, interval - elapsed);
            task.timer = setTimeout(() => this.execute(task), delay);
        }
    }

    /**
     * Request immediate sync for specific resources
     * @param {Object} options 
     */
    requestSync(options) {
        const { resources, reason } = options;
        console.log(`[LiveDataHub] Requesting sync for: ${resources.join(', ')} (Reason: ${reason})`);

        for (const task of this.registry.values()) {
            const hasMatch = (task.resources || []).some(r => resources.includes(r));
            if (hasMatch) {
                // Run immediately if not already polling
                if (!task.isPolling) {
                    if (task.timer) clearTimeout(task.timer);
                    this.execute(task);
                }
            }
        }
    }

    /**
     * Notify that a table has changed (triggered by SSE)
     * @param {string} table 
     */
    notifyRealtime(table) {
        console.log(`[LiveDataHub] Realtime notify for table: ${table}`);
        this.requestSync({ resources: [table], reason: `realtime:${table}` });
    }

    /**
     * Update SSE connection status overlay/ui
     * @param {string} status 
     */
    setRealtimeStatus(status) {
        this.realtimeStatus = status;
        const el = document.getElementById('realtime-indicator');
        if (el) {
            el.className = `status-dot status-dot--${status}`;
            el.title = `Realtime Status: ${status.toUpperCase()}`;
        }
    }
}

window.liveDataHub = new LiveDataHub();
