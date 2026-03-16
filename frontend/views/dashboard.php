<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'HỆ THỐNG GIÁM SÁT VI PHẠM',
    activePage: 'dashboard',
    extraJs: ['/assets/js/pages/DashboardController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="dashboard-header mb-2">
    <div>
        <h1 class="uppercase bold" style="font-size: 1.8rem;">Tổng quan hệ thống</h1>
        <p class="text-dim uppercase" style="font-size: 0.8rem;">Giao diện giám sát thực thi pháp luật • chuẩn US</p>
    </div>
</div>

<div class="metrics-grid mb-2">
    <div class="g-card stat-card">
        <div class="text-dim uppercase bold" style="font-size: 0.7rem;">Tổng camera</div>
        <div class="font-mono bold" style="font-size: 2rem;" id="stat-total-cam">--</div>
    </div>
    <div class="g-card stat-card">
        <div class="text-dim uppercase bold" style="font-size: 0.7rem; color: var(--color-success);">Trực tuyến</div>
        <div class="font-mono bold" style="font-size: 2rem; color: var(--color-success);" id="stat-online-cam">--</div>
    </div>
    <div class="g-card stat-card">
        <div class="text-dim uppercase bold" style="font-size: 0.7rem; color: var(--color-error);">Ngoại tuyến</div>
        <div class="font-mono bold" style="font-size: 2rem; color: var(--color-error);" id="stat-offline-cam">--</div>
    </div>
</div>

<div class="layout-main shadow-glow">
    <div class="panel-cameras">
        <div class="mb-1 uppercase bold"
            style="font-size: 0.8rem; border-left: 3px solid var(--color-primary); padding-left: 12px;">
            Mạng lưới Camera
        </div>
        <div class="camera-grid" id="camera-grid">
            <!-- Loaded by DashboardController -->
        </div>
    </div>

    <aside class="panel-violations">
        <div class="g-card" style="height: 100%; display: flex; flex-direction: column;">
            <div class="g-card__header">
                <span class="g-card__title">Vi phạm thực tế</span>
                <span class="badge badge--online">REALTIME</span>
            </div>
            <div class="g-card__body" id="recent-violations" style="flex:1; overflow-y: auto; padding: 0;">
                <div style="padding: 24px;" class="text-dim uppercase">Đang đồng bộ...</div>
            </div>
        </div>
    </aside>
</div>

<style>
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 24px;
    }

    .stat-card {
        padding: 24px;
    }

    .layout-main {
        display: grid;
        grid-template-columns: 1fr 340px;
        gap: 32px;
    }

    .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 20px;
    }

    .cam-card {
        cursor: pointer;
    }

    .cam-card__media {
        aspect-ratio: 16/9;
        background: #000;
        position: relative;
        overflow: hidden;
    }

    .cam-card__media img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.7;
        transition: opacity 0.3s;
    }

    .cam-card:hover img {
        opacity: 1;
    }

    .cam-card__badge {
        position: absolute;
        top: 12px;
        right: 12px;
        background: rgba(0, 0, 0, 0.8);
        padding: 4px 10px;
        border-radius: 2px;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.1em;
    }

    .violation-item {
        padding: 16px 20px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        gap: 16px;
        cursor: pointer;
        transition: background 0.2s;
        position: relative;
    }

    .violation-item:hover {
        background: var(--color-surface-soft);
    }

    .violation-item__accent {
        width: 3px;
        height: 60%;
        background: var(--color-primary);
        position: absolute;
        left: 0;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>