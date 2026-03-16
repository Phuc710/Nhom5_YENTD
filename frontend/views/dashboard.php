<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'HỆ THỐNG GIÁM SÁT VI PHẠM',
    activePage: 'dashboard',
    extraJs: ['/assets/js/pages/DashboardController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="dashboard-header mb-2 flex-between">
    <div>
        <h1 class="bold uppercase" style="font-size: 2.5rem; line-height: 1.1; letter-spacing: -0.02em;">
            Giám sát <span class="text-primary">Hệ thống</span>
        </h1>
        <p class="text-dim uppercase bold mt-1" style="font-size: 0.7rem; letter-spacing: 0.2em;">
            Hệ thống Quản lý & Giám sát Giao thông
        </p>
    </div>
    <div class="header-actions">
        <span class="badge badge--online" style="padding: 8px 16px; font-size: 0.8rem;">ĐANG HOẠT ĐỘNG</span>
    </div>
</div>

<div class="metrics-grid mb-2">
    <div class="g-card stat-card stat-card--total">
        <div class="stat-card__icon"></div>
        <div class="stat-card__content">
            <div class="text-dim uppercase bold" style="font-size: 0.65rem; letter-spacing: 0.1em;">Tổng số thiết bị
            </div>
            <div class="font-mono bold mt-1" style="font-size: 2.8rem; line-height: 1;" id="stat-total-cam">--</div>
        </div>
    </div>
    <div class="g-card stat-card stat-card--online">
        <div class="stat-card__glow"></div>
        <div class="stat-card__content">
            <div class="text-success uppercase bold" style="font-size: 0.65rem; letter-spacing: 0.1em;">Đang hoạt động
            </div>
            <div class="font-mono bold mt-1" style="font-size: 2.8rem; line-height: 1; color: var(--color-success);"
                id="stat-online-cam">--</div>
        </div>
    </div>
    <div class="g-card stat-card stat-card--offline">
        <div class="stat-card__content">
            <div class="text-error uppercase bold" style="font-size: 0.65rem; letter-spacing: 0.1em;">Mất kết nối
            </div>
            <div class="font-mono bold mt-1" style="font-size: 2.8rem; line-height: 1; color: var(--color-error);"
                id="stat-offline-cam">--</div>
        </div>
    </div>
</div>

<div class="layout-main shadow-glow">
    <div class="panel-cameras">
        <div class="flex-between mb-1" style="border-bottom: 1px solid var(--color-border); padding-bottom: 12px;">
            <div class="uppercase bold" style="font-size: 0.8rem; letter-spacing: 0.1em;">
                <span class="text-primary">01.</span> Điểm Giám Sát AI
            </div>
            <div class="text-dim font-mono" style="font-size: 0.7rem;">NETWORK_SECURE_ENFORCER</div>
        </div>
        <div class="camera-grid" id="camera-grid">
            <!-- Loaded by DashboardController -->
        </div>
    </div>

    <aside class="panel-violations">
        <div class="g-card glass-panel" style="height: 100%; display: flex; flex-direction: column;">
            <div class="g-card__header" style="background: rgba(0, 255, 136, 0.03);">
                <span class="g-card__title">Luồng Sự Kiện</span>
                <div class="live-indicator">
                    <span class="status-dot status-dot--online"></span>
                    <span class="bold" style="font-size: 0.6rem; color: var(--color-success);">TRỰC TIẾP</span>
                </div>
            </div>
            <div class="g-card__body p-0" id="recent-violations" style="flex:1; overflow-y: auto;">
                <div style="padding: 40px; text-align: center;" class="text-dim uppercase bold">
                    <div class="loader-v2 mb-1"></div>
                    Đang Đồng Bộ...
                </div>
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
        padding: 32px;
        position: relative;
        overflow: hidden;
    }

    .stat-card__glow {
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle at center, var(--color-primary-glow) 0%, transparent 60%);
        opacity: 0.1;
        pointer-events: none;
    }

    .stat-card--online {
        background: linear-gradient(135deg, var(--color-surface) 0%, rgba(0, 255, 136, 0.05) 100%);
    }

    .layout-main {
        display: grid;
        grid-template-columns: 1fr 380px;
        gap: 32px;
    }

    .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 24px;
    }

    .cam-card {
        cursor: pointer;
        border-radius: var(--radius-lg);
    }

    .cam-card__media {
        aspect-ratio: 16/10;
        background: #000;
        position: relative;
        overflow: hidden;
    }

    .cam-card__media img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.85;
        transition: transform 0.5s cubic-bezier(0.19, 1, 0.22, 1), opacity 0.3s;
    }

    .cam-card:hover img {
        opacity: 1;
        transform: scale(1.05);
    }

    .cam-card__badge-v2 {
        position: absolute;
        bottom: 16px;
        right: 16px;
        z-index: 10;
    }

    .cam-card__badge-v2 .badge {
        padding: 6px 14px;
        font-size: 0.65rem;
        font-weight: 900;
        letter-spacing: 0.1em;
        border-radius: 4px;
        background: rgba(0, 0, 0, 0.8);
        backdrop-filter: blur(8px);
    }

    .cam-meta-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid var(--color-border);
    }

    .meta-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .meta-label {
        font-size: 0.6rem;
        font-weight: 900;
        color: var(--color-text-dim);
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .meta-value {
        font-size: 0.75rem;
        font-weight: 700;
        color: #fff;
        line-height: 1;
    }

    .no-preview {
        width: 100%;
        height: 100%;
        display: none;
        align-items: center;
        justify-content: center;
        background: #000;
        color: var(--color-text-dim);
        font-family: var(--font-mono);
        font-size: 1rem;
        font-weight: 900;
        letter-spacing: 0.3em;
        text-transform: uppercase;
    }

    .violation-item {
        padding: 20px 24px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        gap: 20px;
        cursor: pointer;
        transition: all 0.2s;
    }

    .violation-item:hover {
        background: rgba(255, 255, 255, 0.03);
    }

    .violation-item__accent {
        width: 4px;
        height: 40px;
        border-radius: 2px;
        background: var(--color-primary);
    }

    .p-0 {
        padding: 0 !important;
    }

    .loader-v2 {
        width: 20px;
        height: 20px;
        border: 2px solid var(--color-border);
        border-top-color: var(--color-primary);
        border-radius: 50%;
        animation: spin 1s linear infinite;
        display: inline-block;
    }

    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>