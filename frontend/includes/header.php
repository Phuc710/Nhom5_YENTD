<?php
use Frontend\App\Core\Page;
use Frontend\App\Auth\Session;

Session::init();
Session::requireLogin();

$page = $page ?? new Page();
$activePage = $page->activePage;
?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page->fullTitle()) ?> | CAMERA AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap"
        rel="stylesheet">

    <?php $variablesCssVersion = @filemtime(__DIR__ . '/../assets/css/variables.css') ?: time(); ?>
    <?php $mainCssVersion = @filemtime(__DIR__ . '/../assets/css/main.css') ?: time(); ?>
    <link rel="stylesheet" href="/assets/css/variables.css?v=<?= $variablesCssVersion ?>">
    <link rel="stylesheet" href="/assets/css/main.css?v=<?= $mainCssVersion ?>">
    <?php foreach ($page->extraCss as $css): ?>
        <?php $cssVersion = @filemtime(__DIR__ . '/..' . $css) ?: time(); ?>
        <link rel="stylesheet" href="<?= htmlspecialchars($css) ?>?v=<?= $cssVersion ?>">
    <?php endforeach; ?>
</head>

<body>
    <div class="app-shell">
        <?php include __DIR__ . '/sidebar.php'; ?>

        <main class="main-view">
            <header class="view-header flex-between mb-2">
                <div class="view-header__breadcrumb">
                    <span class="text-dim uppercase bold" style="font-size: 0.7rem;">Dashboard</span>
                    <span class="text-dim">/</span>
                    <span class="uppercase bold"
                        style="font-size: 0.7rem; color: var(--color-primary);"><?= htmlspecialchars($page->title) ?></span>
                </div>

                <div class="view-header__status flex-between" style="gap: 20px;">
                    <div id="connection-status" class="flex-between" style="gap: 8px;">
                        <span class="status-dot status-dot--online"></span>
                        <span class="uppercase bold" style="font-size: 0.65rem;">Hệ thống trực tuyến</span>
                    </div>
                    <div class="font-mono bold" id="global-clock"
                        style="font-size: 0.9rem; letter-spacing: 0.05em; color: var(--color-primary);">00:00:00</div>
                </div>
            </header>

            <style>
                .view-header {
                    border-bottom: 1px solid var(--color-border);
                    padding-bottom: 16px;
                }
            </style>
