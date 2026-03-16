import UIController from '../core/UIController.js';

/**
 * AnalyticsController - Trí tuệ mạng lưới (AI Trend Visualization)
 */
class AnalyticsController extends UIController {
    constructor() {
        super();
        this.chart = null;
        this.init();
    }

    async init() {
        console.log('📊 AnalyticsController Initializing...');
        await this.loadStats();
    }

    async loadStats() {
        try {
            const apiBase = window.APP_CONFIG?.API_URL || '';
            const res = await fetch(`${apiBase}/api/dashboard/stats/hourly`);
            if (!res.ok) throw new Error('Failed to fetch stats');
            const data = await res.json();

            this.renderChart(data);
            this.showToast('Đã đồng bộ dữ liệu đồ thị', 'success');
        } catch (error) {
            this.setHtml('chart-container', `<div class="text-error font-mono">[ ERROR: ${error.message} ]</div>`);
        }
    }

    renderChart(data) {
        const container = document.getElementById('chart-container');
        if (!container) return;

        // Prepare canvas
        container.innerHTML = '<canvas id="trendChart"></canvas>';
        const ctx = document.getElementById('trendChart').getContext('2d');

        // Extract labels and hours
        // Usually data is { "08": 15, "09": 22 }
        const labels = Object.keys(data).map(h => `${h}:00`);
        const values = Object.values(data);

        // Chart.js configuration (Grok UI / Dark Mode style)
        Chart.defaults.color = '#666';
        Chart.defaults.font.family = "'JetBrains Mono', monospace";

        this.chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Vi phạm ghi nhận',
                    data: values,
                    backgroundColor: 'rgba(59, 130, 246, 0.2)', // Primary var
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                    hoverBackgroundColor: 'rgba(59, 130, 246, 0.4)',
                    borderRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#1f1f1f' }
                    },
                    x: {
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#0a0a0a',
                        titleColor: '#fff',
                        bodyColor: '#3b82f6',
                        borderColor: '#333',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false
                    }
                }
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new AnalyticsController();
});
