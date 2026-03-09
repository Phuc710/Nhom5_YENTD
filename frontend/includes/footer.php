<?php
?>
</main>

<footer class="footer">
    <div class="footer__inner">
        <div>
            <strong><?= htmlspecialchars(APP_NAME) ?></strong>
            <p>Web dieu hanh cho luc luong canh sat va trung tam giam sat giao thong.</p>
        </div>
        <div class="footer__meta">
            <span>Mui gio hien thi: Viet Nam (UTC+7)</span>
            <span>Frontend dung AJAX thong minh va co the nhan trigger tu Supabase Realtime.</span>
        </div>
    </div>
</footer>

<script src="/assets/js/api.js"></script>
<script src="/assets/js/live-data.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script src="/assets/js/realtime.js"></script>
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
