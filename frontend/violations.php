<?php
require_once __DIR__ . '/config.php';
$pageTitle = 'Lịch sử Vi phạm';
$activePage = 'violations';
$extraCss = ['/assets/css/violations.css'];
$extraJs = ['/assets/js/violations.js'];
include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <h1 class="page-header__title">Lịch sử Vi phạm</h1>
        <p class="page-header__subtitle">Tất cả lượt vi phạm giao thông đã ghi nhận</p>
    </div>
    <span id="totalBadge" class="badge badge--gray">Đang tải...</span>
</div>

<!-- Filter -->
<div class="filter-bar">
    <div class="filter-group">
        <label>Camera</label>
        <select id="fCamera">
            <option value="">Tất cả</option>
        </select>
    </div>
    <div class="filter-group">
        <label>Biển số</label>
        <input type="text" id="fPlate" placeholder="51F-12345" maxlength="15">
    </div>
    <div class="filter-group">
        <label>Từ ngày</label>
        <input type="date" id="fFrom">
    </div>
    <div class="filter-group">
        <label>Đến ngày</label>
        <input type="date" id="fTo">
    </div>
    <div class="filter-actions">
        <button class="btn btn--outline btn--sm" onclick="resetFilter()">Xóa lọc</button>
        <button class="btn btn--primary btn--sm" onclick="applyFilter()">Tìm kiếm</button>
    </div>
</div>

<!-- Table -->
<div class="card">
    <div class="table-container">
        <table class="table">
            <thead>
                <tr>
                    <th>Ảnh</th>
                    <th>Biển số</th>
                    <th>Camera · Vị trí</th>
                    <th>Thời gian vi phạm</th>
                    <th>Đèn</th>
                    <th>Confidence</th>
                    <th>Loại</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="violTableBody">
                <tr>
                    <td colspan="8" class="loading">Đang tải...</td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="pagination" id="paginationBar"></div>
</div>

<script>
    window.APP_CONFIG = { API_URL: '<?= API_URL ?>' };
</script>
<?php include __DIR__ . '/includes/footer.php'; ?>