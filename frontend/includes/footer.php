</div> <!-- end main-content -->
</div> <!-- end app-container -->

<footer class="footer-simple">
    <div class="footer-simple__content">
        <span class="text-dim">© 2026 ESP32 Camera Monitoring System</span>
        <div class="footer-simple__links">
            <a href="#" class="text-dim">Tài liệu</a>
            <a href="#" class="text-dim">Hỗ trợ</a>
        </div>
    </div>
</footer>

<style>
    .footer-simple {
        margin-top: 48px;
        padding: 24px 0;
        border-top: var(--border-glass);
    }

    .footer-simple__content {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
    }

    .footer-simple__links {
        display: flex;
        gap: 16px;
    }
</style>

<script src="/assets/js/api.js"></script>
<script src="/assets/js/liveDataHub.js"></script>
<script src="/assets/js/realtime.js"></script>
<script src="/assets/js/ui.js"></script>
<?php foreach ($page->extraJs as $js): ?>
    <script src="<?= htmlspecialchars($js) ?>"></script>
<?php endforeach; ?>

<script>
    function updateClock() {
        const el = document.getElementById('clock');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
        });
    }
    updateClock();
    setInterval(updateClock, 1000);
</script>
</body>

</html>
