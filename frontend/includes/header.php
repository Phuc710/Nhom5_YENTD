<?php
use Frontend\App\Core\Page;
use Frontend\App\Support\Nav;

$page = $page ?? new Page();
$navItems = Nav::items();
?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page->fullTitle()) ?></title>
    <meta name="description" content="He thong giam sat va tra cuu vi pham giao thong.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&family=Rajdhani:wght@600;700&display=swap"
        rel="stylesheet">
    <link rel="stylesheet" href="/assets/css/main.css">
    <?php foreach ($page->extraCss as $css): ?>
        <link rel="stylesheet" href="<?= htmlspecialchars($css) ?>">
    <?php endforeach; ?>
</head>

<body class="app-shell app-shell--<?= htmlspecialchars($page->section) ?>">
    <div class="app-backdrop"></div>

    <header class="navbar">
        <div class="navbar__brand">
            <div class="navbar__logo">
                <span class="navbar__signal navbar__signal--red"></span>
                <span class="navbar__signal navbar__signal--amber"></span>
                <span class="navbar__signal navbar__signal--green"></span>
            </div>
            <div>
                <div class="navbar__eyebrow">Trung tam dieu phoi</div>
                <div class="navbar__title"><?= htmlspecialchars(APP_NAME) ?></div>
            </div>
        </div>

        <nav class="navbar__nav">
            <?php foreach ($navItems as $item): ?>
                <a href="<?= htmlspecialchars($item['href']) ?>"
                    class="navbar__link <?= $page->activePage === $item['key'] ? 'navbar__link--active' : '' ?>">
                    <span><?= htmlspecialchars($item['label']) ?></span>
                </a>
            <?php endforeach; ?>
        </nav>

        <div class="navbar__meta">
            <div class="navbar__badge navbar__badge--live" id="liveSyncBadge" data-live-state="idle">
                <span class="navbar__badge-label">Dong bo live</span>
                <strong id="liveSyncText">Khoi tao</strong>
                <small class="navbar__badge-meta" id="liveSyncMeta">Dang cho du lieu</small>
            </div>
            <button type="button" class="btn btn--outline btn--sm navbar__sync-btn" id="liveSyncBtn">Lam moi</button>
            <div class="navbar__clock">
                <span class="navbar__badge-label">Gio he thong</span>
                <strong id="clock">--:--:--</strong>
            </div>
        </div>
    </header>

    <main class="main-content">
