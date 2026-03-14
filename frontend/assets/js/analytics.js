document.addEventListener('DOMContentLoaded', async () => {
    window.ui?.toast('Đang tổng hợp dữ liệu phân tích...', 'info');

    try {
        // In a real app, you'd fetch specific analytics endpoints
        // For now, we'll use mock data based on recent violations or patterns
        renderCharts();
    } catch (e) {
        window.ui?.toast('Lỗi tải biểu đồ: ' + e.message, 'error');
    }
});

function renderCharts() {
    const ctxTrend = document.getElementById('trendChart')?.getContext('2d');
    const ctxDist = document.getElementById('distributionChart')?.getContext('2d');
    const ctxHourly = document.getElementById('hourlyChart')?.getContext('2d');

    if (ctxTrend) {
        new Chart(ctxTrend, {
            type: 'line',
            data: {
                labels: ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN'],
                datasets: [{
                    label: 'Số vụ vi phạm',
                    data: [12, 19, 15, 8, 22, 30, 25],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: chartOptions()
        });
    }

    if (ctxDist) {
        new Chart(ctxDist, {
            type: 'doughnut',
            data: {
                labels: ['Camera 01', 'Camera 02', 'Camera 03'],
                datasets: [{
                    data: [45, 25, 30],
                    backgroundColor: ['#3b82f6', '#10b981', '#f59e0b'],
                    borderWidth: 0
                }]
            },
            options: {
                ...chartOptions(),
                cutout: '70%'
            }
        });
    }

    if (ctxHourly) {
        new Chart(ctxHourly, {
            type: 'bar',
            data: {
                labels: Array.from({ length: 24 }, (_, i) => `${i}h`),
                datasets: [{
                    label: 'Tin cậy trung bình',
                    data: [5, 2, 1, 0, 1, 3, 10, 25, 45, 30, 20, 15, 12, 18, 22, 35, 50, 60, 40, 30, 20, 15, 10, 8],
                    backgroundColor: '#3b82f6'
                }]
            },
            options: chartOptions()
        });
    }
}

function chartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                labels: { color: '#888', font: { family: 'Inter', size: 11 } }
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#666' }
            },
            x: {
                grid: { display: false },
                ticks: { color: '#666' }
            }
        }
    };
}
