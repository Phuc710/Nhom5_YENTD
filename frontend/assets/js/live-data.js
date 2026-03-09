(function () {
    class LiveDataHub {
        constructor() {
            this.tasks = new Map();
            this.realtimeStatus = 'disabled';
            this.lastRealtimeEventAt = null;
            this.lastSuccessAt = null;

            document.addEventListener('visibilitychange', () => {
                this._rescheduleAll();
                if (!document.hidden) {
                    this.requestSync({ reason: 'tab-visible' });
                }
            });

            window.addEventListener('online', () => {
                this._setBadgeState('live', 'AJAX online', 'Mang da ket noi lai');
                this.requestSync({ reason: 'network-online' });
            });

            window.addEventListener('offline', () => {
                this._setBadgeState('offline', 'Mat mang', 'Dang cho ket noi lai');
            });

            const syncButton = document.getElementById('liveSyncBtn');
            if (syncButton) {
                syncButton.addEventListener('click', () => {
                    this.requestSync({ reason: 'manual-click' });
                });
            }

            this._setBadgeState('idle', 'Khoi tao', 'Dang cho du lieu');
        }

        register(config) {
            const task = {
                id: config.id,
                resources: config.resources || [],
                intervalVisible: config.intervalVisible || 30_000,
                intervalHidden: config.intervalHidden || Math.max((config.intervalVisible || 30_000) * 3, 90_000),
                run: config.run,
                onData: config.onData || (() => {}),
                onError: config.onError || (() => {}),
                timer: null,
                inFlight: false,
                pending: false,
                errorCount: 0,
                disposed: false,
            };

            this.tasks.set(task.id, task);

            if (config.immediate !== false) {
                this.runTask(task.id, 'initial');
            } else {
                this._schedule(task);
            }

            return () => this.unregister(task.id);
        }

        unregister(taskId) {
            const task = this.tasks.get(taskId);
            if (!task) return;
            task.disposed = true;
            if (task.timer) {
                clearTimeout(task.timer);
            }
            this.tasks.delete(taskId);
        }

        async runTask(taskId, reason = 'manual') {
            const task = this.tasks.get(taskId);
            if (!task || task.disposed) return;

            if (task.inFlight) {
                task.pending = true;
                return;
            }

            task.inFlight = true;
            if (task.timer) {
                clearTimeout(task.timer);
                task.timer = null;
            }

            this._setBadgeState('syncing', 'Dang dong bo', this._buildMeta(reason));

            try {
                const data = await task.run({ reason });
                task.errorCount = 0;
                task.onData(data, { reason });
                this.lastSuccessAt = Date.now();
                this._setBadgeState(this._liveStateFromRealtime(), this._statusTitle(), this._statusMeta());
            } catch (error) {
                if (error?.name !== 'AbortError') {
                    task.errorCount += 1;
                    task.onError(error, { reason });
                    this._setBadgeState('degraded', 'Canh bao', `${task.id}: ${error.message}`);
                }
            } finally {
                task.inFlight = false;
                if (task.pending) {
                    task.pending = false;
                    this.runTask(task.id, 'pending');
                    return;
                }
                this._schedule(task);
            }
        }

        requestSync({ resources = [], reason = 'manual' } = {}) {
            const resourceSet = new Set(resources);
            this.tasks.forEach((task) => {
                if (!resourceSet.size || task.resources.some((resource) => resourceSet.has(resource))) {
                    this.runTask(task.id, reason);
                }
            });
        }

        notifyRealtime(tableName) {
            this.lastRealtimeEventAt = Date.now();
            const tableMap = {
                cameras: ['cameras', 'summary'],
                camera_provisioning: ['cameras', 'summary'],
                violations: ['violations', 'summary'],
                detection_zones: ['zones'],
            };
            this.requestSync({ resources: tableMap[tableName] || [], reason: `realtime:${tableName}` });
        }

        setRealtimeStatus(status) {
            this.realtimeStatus = status;
            this._setBadgeState(this._liveStateFromRealtime(), this._statusTitle(), this._statusMeta());
        }

        _schedule(task) {
            if (task.disposed) return;

            const baseInterval = document.hidden ? task.intervalHidden : task.intervalVisible;
            const backoff = task.errorCount ? Math.min(baseInterval * (task.errorCount + 1), 180_000) : baseInterval;
            task.timer = window.setTimeout(() => this.runTask(task.id, 'timer'), backoff);
        }

        _rescheduleAll() {
            this.tasks.forEach((task) => {
                if (task.timer) {
                    clearTimeout(task.timer);
                    task.timer = null;
                }
                if (!task.inFlight) {
                    this._schedule(task);
                }
            });
        }

        _liveStateFromRealtime() {
            if (!navigator.onLine) return 'offline';
            if (this.realtimeStatus === 'subscribed') return 'realtime';
            if (this.realtimeStatus === 'error') return 'degraded';
            return 'live';
        }

        _statusTitle() {
            if (this.realtimeStatus === 'subscribed') {
                return 'Realtime + AJAX';
            }
            if (this.realtimeStatus === 'connecting') {
                return 'Dang noi realtime';
            }
            return 'AJAX thong minh';
        }

        _statusMeta() {
            const parts = [];
            if (this.lastSuccessAt) {
                parts.push(`Cap nhat ${this._formatTime(this.lastSuccessAt)}`);
            }
            if (this.lastRealtimeEventAt && this.realtimeStatus === 'subscribed') {
                parts.push(`Su kien ${this._formatTime(this.lastRealtimeEventAt)}`);
            }
            if (!parts.length) {
                return 'Dang cho du lieu';
            }
            return parts.join(' · ');
        }

        _buildMeta(reason) {
            return `Nguon: ${reason}`;
        }

        _formatTime(timestamp) {
            return new Date(timestamp).toLocaleTimeString('vi-VN', {
                timeZone: (window.APP_CONFIG && window.APP_CONFIG.TIMEZONE) || 'Asia/Ho_Chi_Minh',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
            });
        }

        _setBadgeState(state, title, meta) {
            const badge = document.getElementById('liveSyncBadge');
            const text = document.getElementById('liveSyncText');
            const metaText = document.getElementById('liveSyncMeta');

            if (badge) {
                badge.dataset.liveState = state;
            }
            if (text) {
                text.textContent = title;
            }
            if (metaText) {
                metaText.textContent = meta;
            }
        }
    }

    window.liveDataHub = new LiveDataHub();
})();
