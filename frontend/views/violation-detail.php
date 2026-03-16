<?php
use Frontend\App\Core\Page;

$violationId = $violationId ?? 0;
$page = new Page(
    title: 'HỒ SƠ VI PHẠM',
    activePage: 'violations',
    extraJs: ['/assets/js/pages/ViolationDetailController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-shell">
    <div class="evidence-panel">
        <div class="g-card mb-2">
            <div class="g-card__header">
                <span class="g-card__title">Hiện trường vi phạm</span>
                <span class="badge badge--online" id="v-id">#000000</span>
            </div>
            <div class="evidence-media">
                <img id="v-full-image" src="" alt="Incident Scene">
            </div>
        </div>

        <div class="g-card">
            <div class="g-card__header"><span class="g-card__title">Trích dẫn biển số</span></div>
            <div class="evidence-plate-wrap">
                <img id="v-plate-image" src="" alt="License Plate Crop">
                <div class="plate-text-overlay font-mono" id="v-plate">-- --- --</div>
            </div>
        </div>
    </div>

    <aside class="detail-sidebar">
        <div class="g-card">
            <div class="g-card__header"><span class="g-card__title">Chi tiết kỹ thuật</span></div>
            <div class="g-card__body">
                <div class="detail-list">
                    <div class="detail-item">
                        <div class="detail-label">Thời gian vi phạm</div>
                        <div class="detail-value font-mono" id="v-time">-- : -- : --</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Loại vi phạm</div>
                        <div class="detail-value text-primary" id="v-type">Đang xác định...</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Thiết bị ghi hình</div>
                        <div class="detail-value" id="v-camera">--</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Địa điểm</div>
                        <div class="detail-value" id="v-location">--</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Độ tin cậy AI</div>
                        <div class="detail-value font-mono" id="v-confidence">-- %</div>
                    </div>
                </div>

                <hr style="border:0; border-top:1px solid var(--color-border); margin:20px 0;">

                <button class="btn btn--primary" style="width:100%">XUẤT BIÊN BẢN</button>
            </div>
        </div>
    </aside>
</div>

<style>
    .view-shell {
        display: grid;
        grid-template-columns: 1fr 340px;
        gap: 32px;
    }

    .evidence-media {
        background: #000;
        aspect-ratio: 16/9;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .evidence-media img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }

    .evidence-plate-wrap {
        padding: 32px;
        background: var(--color-surface-soft);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 24px;
    }

    .evidence-plate-wrap img {
        width: 320px;
        border: 1px solid var(--color-border-bright);
    }

    .plate-text-overlay {
        font-size: 2.4rem;
        font-weight: 800;
        color: var(--color-primary);
        letter-spacing: 0.1em;
    }

    .detail-list {
        display: flex;
        flex-direction: column;
        gap: 20px;
    }

    .detail-item {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .detail-label {
        font-size: 0.65rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
    }

    .detail-value {
        font-size: 0.9rem;
        font-weight: 700;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>