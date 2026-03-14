<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Cài đặt hệ thống',
    activePage: 'settings',
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px;">
    <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Cấu hình hệ thống</h1>
    <p class="text-muted">Quản lý các tham số vận hành chung của ứng dụng.</p>
</div>

<div class="settings-grid">
    <div class="card">
        <div class="card__header"><span class="card__title">Thông tin ứng dụng</span></div>
        <div class="card__body">
            <div class="form-group mb-2">
                <label class="form-label">Tên ứng dụng</label>
                <input type="text" class="form-input" value="<?= APP_NAME ?>" readonly>
            </div>
            <div class="form-group mb-2">
                <label class="form-label">Múi giờ</label>
                <input type="text" class="form-input" value="<?= TIMEZONE ?>" readonly>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card__header"><span class="card__title">Dịch vụ Backend</span></div>
        <div class="card__body">
            <div class="form-group mb-2">
                <label class="form-label">API URL</label>
                <input type="text" class="form-input" value="<?= API_URL ?>" readonly>
            </div>
            <div class="form-group mb-2">
                <label class="form-label">Trạng thái kết nối</label>
                <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                    <span class="status-indicator__dot status-indicator__dot--online"></span>
                    <span style="font-weight:600; color:var(--color-success)">ỔN ĐỊNH</span>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .settings-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
        gap: 24px;
    }

    .form-group {
        margin-bottom: 20px;
    }

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
        background: #0a0a0a;
        border: 1px solid #1f1f1f;
        padding: 10px 14px;
        color: #fff;
        border-radius: 4px;
    }
</style>

<?php include __DIR__ . '/../includes/footer.php'; ?>