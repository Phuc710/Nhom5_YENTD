<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Báo cáo vi phạm chi tiết',
    activePage: 'reports',
    extraJs: ['/assets/js/reports.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div>
        <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Báo cáo tổng hợp</h1>
        <p class="text-muted">Dữ liệu chi tiết kèm thời gian chính xác và công cụ sắp xếp.</p>
    </div>
    <div style="display: flex; gap: 12px;">
        <button class="btn btn--outline" onclick="exportReport()">Xuất CSV</button>
    </div>
</div>

<div class="card" style="margin-bottom: 24px;">
    <div class="card__body" style="padding: 24px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 20px; align-items: flex-end;">
            <div class="filter-group">
                <label class="form-label">Khoảng thời gian</label>
                <select id="fRange" class="form-input" onchange="loadReports()">
                    <option value="today">Hôm nay</option>
                    <option value="7d">7 ngày qua</option>
                    <option value="30d">30 ngày qua</option>
                    <option value="all">Tất cả thời gian</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="form-label">Sắp xếp theo thời gian</label>
                <select id="fSort" class="form-input" onchange="loadReports()">
                    <option value="desc">Mới nhất trước</option>
                    <option value="asc">Cũ nhất trước</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="form-label">Thiết bị</label>
                <select id="fCamera" class="form-input" onchange="loadReports()">
                    <option value="">Tất cả Camera</option>
                </select>
            </div>

            <button class="btn btn--primary" style="height: 42px;" onclick="loadReports()">LÀM MỚI</button>
        </div>
    </div>
</div>

<div class="card">
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th style="width: 80px;">ID</th>
                    <th>Thời gian chính xác</th>
                    <th>Biển số</th>
                    <th>Thiết bị / Vị trí</th>
                    <th>Độ tin cậy</th>
                    <th style="text-align: right;">Thao tác</th>
                </tr>
            </thead>
            <tbody id="reportTableBody">
                <tr>
                    <td colspan="6" style="text-align:center; padding:64px;">
                        <div class="spinner" style="margin: 0 auto 16px;"></div>
                        <p class="text-muted">Đang truy xuất dữ liệu báo cáo...</p>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="card__header" id="paginationBar" style="border-top: 1px solid #1f1f1f; background: #050505;"></div>
</div>

<style>
    .form-label {
        display: block;
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--color-text-dim);
        margin-bottom: 8px;
        text-transform: uppercase;
    }

    .form-input {
        width: 100%;
        background: #000;
        border: 1px solid #1f1f1f;
        padding: 10px 14px;
        color: #fff;
        border-radius: 4px;
        font-family: inherit;
    }

    .report-time {
        font-family: monospace;
        font-weight: 600;
        color: var(--color-primary);
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>