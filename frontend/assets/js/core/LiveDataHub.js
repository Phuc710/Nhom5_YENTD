/**
 * LiveDataHub - Bộ điều phối polling và cập nhật dữ liệu nền chuẩn OOP
 */
class LiveDataHub {
    constructor() {
        this.tasks = new Map();
        this.isVisible = !document.hidden;
        this.init();
    }

    init() {
        document.addEventListener('visibilitychange', () => {
            this.isVisible = !document.hidden;
            console.log(`👁️ Visibility changed: ${this.isVisible ? 'VISIBLE' : 'HIDDEN'}`);
            this.adjustIntervals();
        });
    }

    /**
     * @param {object} task { id, run: async fn, onData: fn, intervalVisible, intervalHidden }
     */
    register(task) {
        if (this.tasks.has(task.id)) {
            this.unregister(task.id);
        }

        const taskState = {
            ...task,
            timer: null,
            isExecuting: false
        };

        this.tasks.set(task.id, taskState);
        this.schedule(task.id, 0); // Run immediately
    }

    unregister(id) {
        const task = this.tasks.get(id);
        if (task && task.timer) {
            clearTimeout(task.timer);
        }
        this.tasks.delete(id);
    }

    async execute(id) {
        const task = this.tasks.get(id);
        if (!task || task.isExecuting) return;

        task.isExecuting = true;
        try {
            const data = await task.run();
            if (data && task.onData) task.onData(data);
        } catch (e) {
            if (task.onError) task.onError(e);
        } finally {
            task.isExecuting = false;
            const delay = this.isVisible ? (task.intervalVisible || 5000) : (task.intervalHidden || 30000);
            this.schedule(id, delay);
        }
    }

    schedule(id, delay) {
        const task = this.tasks.get(id);
        if (task) {
            task.timer = setTimeout(() => this.execute(id), delay);
        }
    }

    adjustIntervals() {
        // Logic to immediately update next run could go here
    }
}

const liveDataHub = new LiveDataHub();
export default liveDataHub;
