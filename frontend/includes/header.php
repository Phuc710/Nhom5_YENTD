<?php
use Frontend\App\Core\Page;
use Frontend\App\Support\Nav;
use Frontend\App\Auth\Session;

Session::init();
Session::requireLogin();

$page = $page ?? new Page();
$navItems = Nav::items();
$activePage = $page->activePage;
$username = Session::get('username', 'N/A');
$role = Session::get('role', 'Giám sát');
?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page->fullTitle()) ?></title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/css/main.css">
    <link rel="stylesheet" href="/assets/css/responsive.css">
    <?php foreach ($page->extraCss as $css): ?>
        <link rel="stylesheet" href="<?= htmlspecialchars($css) ?>">
    <?php endforeach; ?>
</head>

<body>
    <div class="app-container">
        <?php include __DIR__ . '/sidebar.php'; ?>

        <div class="main-content">
            <header class="page-header">
                <div class="page-header__breadcrumb">
                    <span class="text-muted">Trang chủ</span>
                    <span class="text-dim">/</span>
                    <span><?= htmlspecialchars($page->title) ?></span>
                </div>

                <div class="page-header__actions">
                    <div class="status-indicator">
                        <span class="status-indicator__dot status-indicator__dot--online"></span>
                        <span class="status-indicator__text">Hệ thống Online</span>
                    </div>
                    <button class="btn btn--outline btn--sm" onclick="location.reload()">
                        Refresh
                    </button>
                    <div class="clock-display" id="clock">00:00:00</div>
                </div>
            </header>

            <style>
                .page-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 32px;
                    padding-bottom: 16px;
                    border-bottom: var(--border-glass);
                }

                .page-header__breadcrumb {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 0.9rem;
                }

                .page-header__actions {
                    display: flex;
                    align-items: center;
                    gap: 20px;
                }

                .status-indicator {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 0.85rem;
                    font-weight: 500;
                }

                .status-indicator__dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                }

                .status-indicator__dot--online {
                    background: var(--color-success);
                    box-shadow: 0 0 10px var(--color-success);
                }

                .clock-display {
                    font-family: monospace;
                    font-size: 1.1rem;
                    font-weight: 600;
                    color: var(--color-primary);
                    background: var(--color-surface-soft);
                    padding: 6px 12px;
                    border-radius: var(--radius-sm);
                }

                .text-dim {
                    color: var(--color-text-dim);
                }
            </style>