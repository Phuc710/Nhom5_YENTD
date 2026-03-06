<?php
/**
 * includes/footer.php — Footer + global scripts
 */
?>
</main><!-- /.main-content -->

<footer class="footer">
    <p>©
        <?= date('Y') ?>
        <?= APP_NAME ?> · Múi giờ: Việt Nam (UTC+7)
    </p>
</footer>

<script src="/assets/js/api.js"></script>
<?php if (isset($extraJs)):
    foreach ($extraJs as $js): ?>
        <script src="<?= $js ?>"></script>
    <?php endforeach; endif; ?>

<script>
    // Đồng hồ realtime
    function updateClock() {
        const el = document.getElementById('clock');
        if (!el) return;
        const now = new Date();
        el.textContent = now.toLocaleTimeString('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
        });
    }
    updateClock();
    setInterval(updateClock, 1000);
</script>
</body>

</html>