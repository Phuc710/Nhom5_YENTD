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

<div class="view-header mb-3">
    <div class="flex-between">
        <div>
            <h1 class="bold uppercase" style="font-size: 2.2rem; line-height: 1; letter-spacing: -0.02em;">
                Hồ sơ <span class="text-primary">Vi phạm</span>
            </h1>
            <p class="text-dim uppercase bold mt-1" style="font-size: 0.65rem; letter-spacing: 0.15em;">
                Dữ liệu ghi nhận #<span id="v-id-head">000000</span> • Hệ thống giám sát giao thông
            </p>
        </div>
        <button class="btn btn--outline btn--sm" onclick="history.back()">QUAY LẠI</button>
    </div>
</div>

<div class="view-shell">
    <div class="evidence-panel">
        <div class="g-card g-card--glass mb-3">
            <div class="g-card__header border-bottom flex-between">
                <span class="g-card__title">Hình ảnh hiện trường</span>
                <span class="badge badge--online" id="v-id">#000000</span>
            </div>
            <div class="evidence-media-v2">
                <img id="v-full-image" src="" alt="Incident Scene">
                <div class="media-overlay-id font-mono">DỮ LIỆU GHI HÌNH</div>
            </div>
        </div>

        <div class="g-card g-card--glass">
            <div class="g-card__header border-bottom"><span class="g-card__title">Hình ảnh biển số</span></div>
            <div class="evidence-plate-wrap-v2">
                <div class="plate-canvas-frame">
                    <img id="v-plate-image" src="" alt="License Plate Crop">
                </div>
                <div class="plate-identity">
                    <div class="text-dim uppercase bold" style="font-size: 0.65rem; letter-spacing: 0.1em;">Biển số nhận
                        diện</div>
                    <div class="plate-text-glow font-mono" id="v-plate">-- --- --</div>
                </div>
            </div>
        </div>
    </div>

    <aside class="detail-sidebar">
        <div class="g-card g-card--glass">
            <div class="g-card__header border-bottom"><span class="g-card__title">Thông tin chi tiết</span></div>
            <div class="g-card__body p-3">
                <div class="detail-list-v2">
                    <div class="detail-item-v2">
                        <div class="label-v2">Thời gian ghi nhận</div>
                        <div class="value-v2 font-mono" id="v-time">-- : -- : --</div>
                    </div>
                    <div class="detail-item-v2">
                        <div class="label-v2">Loại vi phạm</div>
                        <div class="value-v2 text-primary" id="v-type"
                            style="text-shadow: 0 0 10px var(--glow-primary);">ĐANG XỬ LÝ...</div>
                    </div>
                    <div class="detail-item-v2">
                        <div class="label-v2">Camera ghi hình</div>
                        <div class="value-v2" id="v-camera">--</div>
                    </div>
                    <div class="detail-item-v2">
                        <div class="label-v2">Địa điểm</div>
                        <div class="value-v2" id="v-location">--</div>
                    </div>
                    <div class="detail-item-v2">
                        <div class="label-v2">Độ chính xác AI</div>
                        <div class="value-v2 font-mono" id="v-confidence">-- %</div>
                    </div>
                </div>

                <div class="action-grid mt-4">
                    <button class="btn btn--primary" style="width:100%">XUẤT BÁO CÁO (PDF)</button>
                    <button class="btn btn--outline mt-2" style="width:100%; font-size: 0.7rem;">CHUYỂN TIẾP XỬ
                        LÝ</button>
                </div>
            </div>
        </div>
    </aside>
</div>

<style>
    .view-shell {
        display: grid;
        grid-template-columns: 1fr 360px;
        gap: 24px;
    }

    .evidence-media-v2 {
        background: #000;
        aspect-ratio: 16/9;
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 0 0 8px 8px;
    }

    .evidence-media-v2 img {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }

    .media-overlay-id {
        position: absolute;
        bottom: 12px;
        right: 12px;
        font-size: 0.55rem;
        color: var(--color-primary);
        background: rgba(0, 0, 0, 0.6);
        padding: 4px 8px;
        border: 1px solid var(--color-primary-dim);
        border-radius: 4px;
    }

    .evidence-plate-wrap-v2 {
        padding: 24px;
        display: flex;
        align-items: center;
        gap: 32px;
    }

    .plate-canvas-frame {
        width: 240px;
        background: #000;
        border: 1px solid var(--color-border-bright);
        padding: 8px;
        border-radius: 4px;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4);
    }

    .plate-canvas-frame img {
        width: 100%;
        display: block;
    }

    .plate-text-glow {
        font-size: 2.2rem;
        font-weight: 800;
        color: var(--color-primary);
        letter-spacing: 0.05em;
        text-shadow: 0 0 20px var(--glow-primary);
    }

    .detail-list-v2 {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .detail-item-v2 {
        border-bottom: 1px solid var(--color-border-soft);
        padding-bottom: 12px;
    }

    .label-v2 {
        font-size: 0.6rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
        margin-bottom: 4px;
        letter-spacing: 0.1em;
    }

    .value-v2 {
        font-size: 0.95rem;
        font-weight: 700;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>