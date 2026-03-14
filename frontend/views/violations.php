<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Nhật ký Vi phạm',
    activePage: 'violations',
    extraCss: ['/assets/css/violations.css'],
    extraJs: ['/assets/js/violations.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div>
        <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Nhật ký vi phạm</h1>
        <p class="text-muted">Dữ liệu phát hiện từ hệ thống AI Camera.</p>
    </div>
    <span id="totalBadge" class="badge badge--online">KẾT NỐI: ONLINE</span>
</div>

<!-- Grok UI Filter Bar -->
<div class="card" style="margin-bottom: 24px; border-color: #1f1f1f; background: #050505;">
    <div class="card__body" style="padding: 24px;">
        <div style="display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 24px;">
            <div class="filter-group">
                <label class="form-label">Tìm kiếm biển số</label>
                <input type="text" id="fPlate" class="form-input"
                    style="font-size: 1.1rem; font-weight: 700; text-transform: uppercase;" placeholder="Nhập BSX..."
                    oninput="onSearchInput()">
            </div>

            <div class="filter-group">
                <label class="form-label">Thời gian</label>
                <div style="display: flex; gap: 4px;">
                    <button class="btn btn--outline btn--sm active-preset" data-range="all"
                        onclick="setDateRange('all', this)">ALL</button>
                    <button class="btn btn--outline btn--sm" data-range="today"
                        onclick="setDateRange('today', this)">24H</button>
                    <button class="btn btn--outline btn--sm" data-range="7d"
                        onclick="setDateRange('7d', this)">7D</button>
                </div>
            </div>

            <div class="filter-group">
                <label class="form-label">Thiết bị</label>
                <select id="fCamera" class="form-input" onchange="applyFilter()">
                    <option value="">TẤT CẢ CAMERA</option>
                </select>
            </div>
        </div>
    </div>
</div>

<div class="card">
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Hiện trường</th>
                    <th>Biển số</th>
                    <th>Camera / Vị trí</th>
                    <th>Thời gian</th>
                    <th>Tin cậy</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="violTableBody">
                <tr>
                    <td colspan="6" style="text-align:center; padding:64px;">
                        <div class="spinner" style="margin: 0 auto 16px;"></div>
                        <p class="text-muted">Đang truy xuất dữ liệu...</p>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="card__header" id="paginationBar" style="border-top: 1px solid #1f1f1f; background: #050505;">
        <!-- Pagination via JS -->
    </div>
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

    .form-input:focus {
        border-color: var(--color-primary);
        outline: none;
    }

    .active-preset {
        background: var(--color-primary) !important;
        color: #fff !important;
        border-color: var(--color-primary) !important;
    }

    .plate-badge {
        background: #111;
        color: #fff;
        padding: 4px 10px;
        border-radius: 4px;
        border: 1px solid #333;
        font-family: monospace;
        font-weight: 700;
        font-size: 1.1rem;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>