<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Hệ thống Camera',
    activePage: 'dashboard',
    extraCss: ['/assets/css/pages/dashboard.css'],
    extraJs: ['/assets/js/dashboard.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="dashboard-layout">
    <div class="dashboard-main">
        <div class="camera-grid" id="cameraGrid">
            <div class="loading-state" style="grid-column: 1/-1; text-align: center; padding: 64px;">
                <div class="spinner" style="margin: 0 auto 16px;"></div>
                <p class="text-muted">Đang kết nối hệ thống...</p>
            </div>
        </div>
    </div>

    <aside class="dashboard-sidebar">
        <div class="card" style="height: 100%; display: flex; flex-direction: column;">
            <div class="card__header">
                <span class="card__title">Vi phạm vừa mới phát hiện</span>
                <span class="badge badge--online" id="liveLabel">LIVE</span>
            </div>
            <div class="card__body" id="recentActivity" style="flex:1; overflow-y: auto; padding: 0;">
                <!-- Filled by JS -->
                <div style="padding: 24px; text-align: center;" class="text-muted">Đang cập nhật...</div>
            </div>
            <div class="card__header" style="border-top: 1px solid #1f1f1f; border-bottom: none;">
                <a href="/violations" class="text-primary"
                    style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">Xem tất cả nhật ký</a>
            </div>
        </div>
    </aside>
</div>

<style>
    .dashboard-layout {
        display: grid;
        grid-template-columns: 1fr 320px;
        gap: 32px;
        align-items: start;
    }

    @media (max-width: 1200px) {
        .dashboard-layout {
            grid-template-columns: 1fr;
        }
    }

    .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 24px;
    }

    .cam-card {
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
        border: 1px solid #1f1f1f;
    }

    .cam-card:hover {
        border-color: var(--color-primary);
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
    }

    .cam-card__preview {
        width: 100%;
        aspect-ratio: 16/9;
        background: #050505;
        position: relative;
        overflow: hidden;
    }

    .cam-card__preview img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.8;
    }

    .cam-card__body {
        padding: 20px;
    }

    .cam-card__title {
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .cam-card__meta {
        font-size: 0.8rem;
        color: var(--color-text-dim);
    }

    .cam-card__status {
        position: absolute;
        top: 12px;
        right: 12px;
    }

    /* Activity Feed Styles */
    .activity-item {
        display: flex;
        gap: 12px;
        padding: 12px 16px;
        border-bottom: 1px solid #141414;
        cursor: pointer;
        transition: background 0.2s;
        align-items: center;
    }

    .activity-item:hover {
        background: #0a0a0a;
    }

    .activity-thumb {
        width: 50px;
        height: 32px;
        object-fit: cover;
        border-radius: 2px;
    }

    .activity-plate {
        font-size: 0.85rem;
        font-weight: 800;
        color: #fff;
    }

    .activity-meta {
        font-size: 0.7rem;
        color: var(--color-text-dim);
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>