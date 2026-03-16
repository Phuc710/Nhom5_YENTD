<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'XUẤT BÁO CÁO',
    activePage: 'reports',
    extraJs: ['/assets/js/pages/ReportsController.js']
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2">
    <div class="flex-between">
        <div>
            <h1 class="uppercase bold" style="font-size: 1.5rem;">Quản lý báo cáo</h1>
            <p class="text-dim uppercase" style="font-size: 0.7rem;">Tạo và xuất báo cáo vi phạm</p>
        </div>
        <button id="btn-export" class="btn btn--primary">XUẤT BÁO CÁO (PDF)</button>
    </div>
</div>

<div class="g-card" style="padding: 120px; text-align: center; border-style: dashed;">
    <div class="font-mono text-dim mb-1" style="font-size: 1.2rem;">[ CHƯA CÓ DỮ LIỆU ]</div>
    <p class="text-dim uppercase bold">Chọn các vi phạm từ Nhật ký để tạo báo cáo.</p>
</div>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>