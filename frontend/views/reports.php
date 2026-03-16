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
            <h1 class="uppercase bold" style="font-size: 1.5rem;">Hồ sơ báo cáo pháp lý</h1>
            <p class="text-dim uppercase" style="font-size: 0.7rem;">Tạo và xuất biên bản vi phạm theo định dạng chuẩn
            </p>
        </div>
        <button id="btn-export" class="btn btn--primary">XUẤT BIÊN BẢN (PDF)</button>
    </div>
</div>

<div class="g-card" style="padding: 120px; text-align: center; border-style: dashed;">
    <div class="font-mono text-dim mb-1" style="font-size: 1.2rem;">[ BIỂU MẪU ĐANG TRỐNG ]</div>
    <p class="text-dim uppercase bold">Chọn các vi phạm từ Nhật ký để tự động tạo báo cáo chuyên án.</p>
</div>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>