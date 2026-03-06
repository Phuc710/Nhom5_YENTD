<?php
/**
 * includes/header.php — Header chung + Navigation
 * Nhận $pageTitle và $activePage từ trang gọi.
 */
$pageTitle = $pageTitle ?? APP_NAME;
$activePage = $activePage ?? 'dashboard';
?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($pageTitle) ?> — <?= APP_NAME ?></title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/css/main.css">
    <?php if (isset($extraCss)):
        foreach ($extraCss as $css): ?>
            <link rel="stylesheet" href="<?= $css ?>">
        <?php endforeach; endif; ?>
</head>

<body>

    <nav class="navbar">
        <div class="navbar__brand">
            <svg class="navbar__logo" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="32" height="32" rx="8" fill="#DC2626" />
                <circle cx="16" cy="10" r="3.5" fill="white" opacity="0.9" />
                <circle cx="16" cy="20" r="3.5" fill="#22C55E" />
                <circle cx="16" cy="10" r="2" fill="#DC2626" />
            </svg>
            <span class="navbar__title"><?= APP_NAME ?></span>
        </div>

        <ul class="navbar__links">
            <li>
                <a href="/index.php"
                    class="navbar__link <?= $activePage === 'dashboard' ? 'navbar__link--active' : '' ?>">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path
                            d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
                    </svg>
                    Dashboard
                </a>
            </li>
            <li>
                <a href="/violations.php"
                    class="navbar__link <?= $activePage === 'violations' ? 'navbar__link--active' : '' ?>">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd"
                            d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                            clip-rule="evenodd" />
                    </svg>
                    Lịch sử Vi phạm
                </a>
            </li>
        </ul>

        <div class="navbar__time" id="clock">--:--:--</div>
    </nav>

    <main class="main-content">