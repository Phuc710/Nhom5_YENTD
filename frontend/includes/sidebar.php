<?php
/**
 * Sidebar Component - Grok UI / Enforcement Style
 */
?>
<aside class="sidebar">
    <div class="sidebar__brand">
        <div class="brand-box">C</div>
        <div class="brand-text">CAMERA <span>AI</span></div>
    </div>

    <nav class="sidebar__nav">
        <div class="nav-group">
            <div class="nav-label">Phân tích & Giám sát</div>
            <a href="/" class="nav-link <?= $activePage === 'dashboard' ? 'active' : '' ?>">
                <div class="nav-link__icon"></div>
                <span>Tổng quan</span>
            </a>
            <a href="/violations" class="nav-link <?= $activePage === 'violations' ? 'active' : '' ?>">
                <div class="nav-link__icon"></div>
                <span>Nhật ký vi phạm</span>
            </a>
        </div>

        <div class="nav-group">
            <div class="nav-label">Quản lý mạng lưới</div>
            <a href="/cameras" class="nav-link <?= $activePage === 'cameras' ? 'active' : '' ?>">
                <div class="nav-link__icon"></div>
                <span>Danh sách thiết bị</span>
            </a>
            <a href="/settings" class="nav-link <?= $activePage === 'settings' ? 'active' : '' ?>">
                <div class="nav-link__icon"></div>
                <span>Cấu hình hệ thống</span>
            </a>
        </div>
    </nav>

    <div class="sidebar__footer">
        <div class="user-info">
            <div class="user-avatar">AD</div>
            <div class="user-meta">
                <div class="user-name">Administrator</div>
                <a href="/logout" class="logout-link">Đăng xuất</a>
            </div>
        </div>
    </div>
</aside>

<style>
    .sidebar {
        width: var(--sidebar-width);
        background: var(--color-surface);
        border-right: 1px solid var(--color-border);
        height: 100vh;
        position: fixed;
        display: flex;
        flex-direction: column;
        z-index: 100;
    }

    .sidebar__brand {
        padding: 40px 24px;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .brand-box {
        width: 32px;
        height: 32px;
        background: var(--color-primary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        color: #fff;
        border-radius: 2px;
    }

    .brand-text {
        font-weight: 800;
        letter-spacing: 0.15em;
        font-size: 0.9rem;
    }

    .brand-text span {
        color: var(--color-text-dim);
        font-weight: 400;
    }

    .sidebar__nav {
        flex: 1;
        padding: 0 16px;
    }

    .nav-group {
        margin-bottom: 32px;
    }

    .nav-label {
        padding: 0 12px;
        margin-bottom: 12px;
        font-size: 0.65rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
        letter-spacing: 0.1em;
    }

    .nav-link {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        color: var(--color-text-muted);
        font-weight: 700;
        font-size: 0.85rem;
        transition: all 0.2s;
        border-radius: 2px;
    }

    .nav-link:hover {
        background: var(--color-surface-soft);
        color: var(--color-text);
    }

    .nav-link.active {
        background: var(--color-surface-soft);
        color: var(--color-primary);
    }

    .nav-link__icon {
        width: 4px;
        height: 4px;
        background: currentColor;
        border-radius: 50%;
    }

    .sidebar__footer {
        padding: 24px;
        border-top: 1px solid var(--color-border);
    }

    .user-info {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px;
        background: var(--color-surface-soft);
        border: 1px solid var(--color-border);
    }

    .user-avatar {
        width: 32px;
        height: 32px;
        background: #333;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        font-weight: 800;
        border-radius: 2px;
    }

    .user-name {
        font-size: 0.8rem;
        font-weight: 700;
        color: #fff;
    }

    .logout-link {
        font-size: 0.7rem;
        color: var(--color-primary);
        text-decoration: underline;
    }
</style>