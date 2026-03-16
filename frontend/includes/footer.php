</main>
</div>

<footer class="app-footer flex-between">
    <div class="text-dim uppercase bold" style="font-size: 0.65rem;">&copy; 2026 CAMERA AI NETWORK • SECURED NODE
    </div>
    <div class="flex-between" style="gap: 24px; font-size: 0.65rem;">
        <a href="#" class="text-dim hover-white uppercase bold">Tài liệu API</a>
        <a href="#" class="text-dim hover-white uppercase bold">Hỗ trợ kỹ thuật</a>
    </div>
</footer>

<style>
    .app-footer {
        margin-left: var(--sidebar-width);
        padding: 24px 32px;
        border-top: 1px solid var(--color-border);
        background: var(--color-bg);
    }

    .hover-white:hover {
        color: #fff;
    }
</style>

<!-- Global App Config -->
<?= $page->configScript() ?>

<!-- Load OOP JS Core & Services -->
<script type="module">
    function updateClock() {
        const el = document.getElementById('global-clock');
        if (el) el.textContent = new Date().toLocaleTimeString('vi-VN', { hour12: false });
    }
    setInterval(updateClock, 1000);
    updateClock();
</script>

<?php foreach ($page->extraJs as $js): ?>
    <?php $jsVersion = @filemtime(__DIR__ . '/..' . $js) ?: time(); ?>
    <script type="module" src="<?= htmlspecialchars($js) ?>?v=<?= $jsVersion ?>"></script>
<?php endforeach; ?>
</body>

</html>
