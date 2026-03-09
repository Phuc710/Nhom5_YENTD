<?php
require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Page;

$page = new Page(
    title: 'Tất cả vi phạm',
    activePage: 'violations',
    extraCss: ['/assets/css/violations.css'],
    extraJs: ['/assets/js/violations.js'],
    section: 'admin',
);

include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <h1 class="page-header__title">Toàn bộ vi phạm giao thông</h1>
        <p class="page-header__subtitle">
            Xem danh sách vi phạm chi tiết với thời gian, camera, vị trí, trạng thái đèn, confidence và liên kết sang
            trang hồ sơ đầy đủ.
        </p>
    </div>
    <span id="totalBadge" class="badge badge--gray">Đang tải...</span>
</div>

<div class="filter-bar">
    <div class="filter-group">
        <label>Camera</label>
        <select id="fCamera">
            <option value="">Tất cả</option>
        </select>
    </div>
    <div class="filter-group">
        <label>Biển số</label>
        <input type="text" id="fPlate" placeholder="51A12345" maxlength="15">
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

<div class="card">
    <div class="table-container">
        <table class="table">
            <thead>
                <tr>
                    <th>Ảnh</th>
                    <th>Biển số</th>
                    <th>Camera · Vị trí</th>
                    <th>Ngày giờ</th>
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

<?= $page->configScript() ?>

<?php include __DIR__ . '/includes/footer.php'; ?>
