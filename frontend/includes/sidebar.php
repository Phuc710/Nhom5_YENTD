<?php
/**
 * Shared Sidebar Component
 */
?>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>

<header class="mobile-header">
    <div style="display:flex; align-items:center; gap:12px;">
        <div class="logo-icon" style="width:28px; height:28px; font-size:0.8rem;">Y</div>
        <span style="font-weight:700; font-size:0.9rem;">YTD MONITORING</span>
    </div>
    <button class="btn btn--outline" style="padding:4px 8px;" onclick="toggleSidebar()">
        DANH MỤC
    </button>
</header>

<aside class="sidebar" id="sidebar">
    <div class="sidebar__logo">
        <span class="logo-icon">Y</span>
        <span class="logo-text">YTD <strong>Monitoring</strong></span>
    </div>

    <nav class="sidebar__nav">
        <div class="nav-group">
            <span class="nav-group__label">Giám sát</span>
            <a href="/" class="nav-item <?= $activePage === 'dashboard' ? 'active' : '' ?>">
                <i class="icon-dashboard"></i>
                <span>Tổng quan</span>
            </a>
            <a href="/violations" class="nav-item <?= $activePage === 'violations' ? 'active' : '' ?>">
                <i class="icon-alert"></i>
                <span>Vi phạm</span>
            </a>
            <a href="/reports" class="nav-item <?= $activePage === 'reports' ? 'active' : '' ?>">
                <i class="icon-report"></i>
                <span>Báo cáo</span>
            </a>
            <a href="/analytics" class="nav-item <?= $activePage === 'analytics' ? 'active' : '' ?>">
                <i class="icon-chart"></i>
                <span>Phân tích</span>
            </a>
        </div>

        <div class="nav-group">
            <span class="nav-group__label">Hệ thống</span>
            <a href="/cameras" class="nav-item <?= $activePage === 'cameras' ? 'active' : '' ?>">
                <i class="icon-camera"></i>
                <span>Thiết bị</span>
            </a>
            <a href="/settings" class="nav-item <?= $activePage === 'settings' ? 'active' : '' ?>">
                <i class="icon-settings"></i>
                <span>Cài đặt</span>
            </a>
        </div>
    </nav>

    <div class="sidebar__footer">
        <div class="user-pill">
            <div class="user-pill__avatar">P</div>
            <div class="user-pill__info">
                <span class="user-name">Admin</span>
                <a href="/logout" class="user-role" style="color:var(--color-primary); text-decoration: underline;">Đăng
                    xuất</a>
            </div>
        </div>
    </div>
</aside>

<style>
    .sidebar {
        width: var(--sidebar-width);
        height: 100vh;
        background: var(--color-surface);
        border-right: var(--border-glass);
        position: fixed;
        top: 0;
        left: 0;
        display: flex;
        flex-direction: column;
        z-index: 1000;
    }

    .sidebar__logo {
        padding: 32px 24px;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .logo-icon {
        width: 32px;
        height: 32px;
        background: var(--grad-primary);
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        color: white;
    }

    .logo-text {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--color-text-main);
        text-transform: uppercase;
        letter-spacing: -0.02em;
    }

    .sidebar__nav {
        flex: 1;
        padding: 0 16px;
    }

    .nav-group {
        margin-bottom: 24px;
    }

    .nav-group__label {
        display: block;
        padding: 0 12px;
        margin-bottom: 8px;
        font-size: 0.7rem;
        font-weight: 800;
        color: var(--color-text-dim);
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    .nav-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        color: var(--color-text-muted);
        font-weight: 600;
        transition: all 0.2s ease;
        font-size: 0.85rem;
    }

    .nav-item:hover {
        background: var(--color-surface-soft);
        color: var(--color-text-main);
    }

    .nav-item.active {
        background: var(--color-surface-soft);
        color: var(--color-primary);
        border-right: 3px solid var(--color-primary);
    }

    .sidebar__footer {
        padding: 24px;
        border-top: var(--border-glass);
    }

    .user-pill {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px;
        border-radius: 4px;
        background: #050505;
        border: 1px solid #1f1f1f;
    }

    .user-pill__avatar {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: var(--color-primary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
    }

    .user-pill__info {
        display: flex;
        flex-direction: column;
    }

    .user-name {
        font-size: 0.85rem;
        font-weight: 700;
    }

    .user-role {
        font-size: 0.7rem;
        color: var(--color-text-dim);
    }
</style>

<script>
    function toggleSidebar() {
        const s = document.getElementById('sidebar');
        const o = document.getElementById('sidebarOverlay');
        if (s) s.classList.toggle('show');
        if (o) o.classList.toggle('show');
    }
</script>