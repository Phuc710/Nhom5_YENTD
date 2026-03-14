let currentParams = {
    page: 1,
    limit: 20
};

document.addEventListener('DOMContentLoaded', () => {
    initFilters();
    loadReports();
});

async function initFilters() {
    try {
        const cameras = await api.getCameras();
        const select = document.getElementById('fCamera');
        if (select) {
            cameras.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.camera_id || c.id;
                opt.textContent = c.camera_name || `Camera ${c.id}`;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Lỗi tải danh sách camera:', e);
    }
}

async function loadReports() {
    const tbody = document.getElementById('reportTableBody');
    if (!tbody) return;

    const params = {
        page: currentParams.page,
        limit: currentParams.limit,
        camera_id: document.getElementById('fCamera').value,
        range: document.getElementById('fRange').value,
        sort: document.getElementById('fSort').value
    };

    try {
        const response = await api.getViolations(params);
        // Assuming the API supports sorting or we handle it client-side if the API is simple
        // For now, we trust the API or handle what we can.
        renderReportTable(response);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--color-error);">Lỗi: ${e.message}</td></tr>`;
    }
}

function renderReportTable(data) {
    const tbody = document.getElementById('reportTableBody');
    const violations = Array.isArray(data) ? data : (data.items || []);

    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:48px;" class="text-muted">Không tìm thấy dữ liệu phù hợp.</td></tr>';
        return;
    }

    tbody.innerHTML = violations.map(v => `
        <tr>
            <td class="text-muted">#${v.id}</td>
            <td><span class="report-time">${formatFullTime(v.timestamp)}</span></td>
            <td><span class="plate-badge">${v.license_plate || '---'}</span></td>
            <td>
                <div style="font-weight:700;">${v.camera_name || 'Cam #' + v.camera_id}</div>
                <div class="text-dim" style="font-size:0.75rem;">${v.location || '--'}</div>
            </td>
            <td><span class="text-primary" style="font-weight:700;">${v.confidence ? (v.confidence * 100).toFixed(2) + '%' : '--'}</span></td>
            <td style="text-align: right;">
                <a href="/violation-detail?id=${v.id}" class="btn btn--outline btn--sm">Chi tiết</a>
            </td>
        </tr>
    `).join('');
}

function formatFullTime(iso) {
    if (!iso) return '--';
    const d = new Date(iso);
    const date = d.toLocaleDateString('vi-VN');
    const time = d.toLocaleTimeString('vi-VN', { hour12: false });
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${date} ${time}.${ms}`;
}

function exportReport() {
    window.ui?.toast('Đang chuẩn bị dữ liệu CSV...', 'info');
    // Implementation for CSV export would go here
    setTimeout(() => {
        window.ui?.toast('Tính năng xuất báo cáo sẽ khả dụng sau khi kết nối Database chính thức.', 'success');
    }, 1500);
}
