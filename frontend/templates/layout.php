<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title><?= htmlspecialchars($title ?? 'Camera AI') ?></title>
    <link rel="stylesheet" href="/assets/css/base.css">
    <link rel="stylesheet" href="/assets/css/components.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
</head>

<body>
    <script>
        window.APP_CONFIG = {
            apiBaseUrl: <?= json_encode($apiBaseUrl, JSON_UNESCAPED_SLASHES); ?>,
            currentPath: <?= json_encode($currentPath ?? '/', JSON_UNESCAPED_SLASHES); ?>,
            appTitle: <?= json_encode($title ?? 'Camera AI'); ?>,
            localLanIp: <?= json_encode(App\Core\Config::get('LOCAL_LAN_IP', 'localhost')); ?>,
            mqttWsPort: <?= json_encode(App\Core\Config::get('MQTT_WS_PORT', '9001')); ?>
        };
    </script>

    <div class="shell">
        <aside class="sidebar">
            <div class="sidebar__header">
                <p class="eyebrow">Local Monitor</p>
                <h1>Camera AI</h1>
            </div>

            <nav class="sidebar__nav">
                <a href="/dashboard" class="nav-link" data-route="dashboard">
                    <i class="fa-solid fa-chart-line fa-fw"></i>
                    <span>Dashboard</span>
                </a>
                <a href="/cameras" class="nav-link" data-route="cameras">
                    <i class="fa-solid fa-camera fa-fw"></i>
                    <span>Cameras</span>
                </a>
                <a href="/violations" class="nav-link" data-route="violations">
                    <i class="fa-solid fa-triangle-exclamation fa-fw"></i>
                    <span>Violations</span>
                </a>
                <a href="/settings" class="nav-link" data-route="settings">
                    <i class="fa-solid fa-sliders fa-fw"></i>
                    <span>Settings</span>
                </a>
            </nav>

            <div class="sidebar__footer">
                <a id="apiHealthLink" class="button button--ghost button--full" href="<?= htmlspecialchars($apiBaseUrl) ?>/health"
                    target="_blank" rel="noreferrer">
                    <i class="fa-solid fa-heart-pulse"></i> Health
                </a>
                <div class="system-status">
                    <div id="backendConnectionDot" class="status-dot"></div>
                    <span id="backendConnectionText">Connecting...</span>
                </div>
                <button id="reconnectBackendBtn" class="button button--ghost button--full mt-2" type="button" style="display: none;">
                    <i class="fa-solid fa-plug"></i> Connect Backend
                </button>
                <div class="system-info">
                    <span id="server-ip">...</span>
                </div>
            </div>
        </aside>

        <main class="content">
            <div id="view-dashboard" class="app-view" hidden>
                <section class="hero">
                    <div>
                        <p class="eyebrow">Overview</p>
                        <h2>Dashboard</h2>
                        <p class="muted">Tổng quan hệ thống camera, stream và vi phạm theo dữ liệu backend.</p>
                    </div>
                </section>

                <div class="dashboard-grid">
                    <div class="stat-card panel">
                        <div class="stat-card__icon"><i class="fa-solid fa-bolt"></i></div>
                        <div class="stat-card__info">
                            <dt>Vi phạm hôm nay</dt>
                            <dd id="stat-total-today">0</dd>
                        </div>
                    </div>
                    <div class="stat-card panel">
                        <div class="stat-card__icon"><i class="fa-solid fa-camera"></i></div>
                        <div class="stat-card__info">
                            <dt>Camera online</dt>
                            <dd id="stat-online-cameras">0/0</dd>
                        </div>
                    </div>
                    <div class="stat-card panel">
                        <div class="stat-card__icon"><i class="fa-solid fa-microchip"></i></div>
                        <div class="stat-card__info">
                            <dt>AI status</dt>
                            <dd id="stat-ai-status">Ready</dd>
                        </div>
                    </div>
                </div>

                <div class="layout-grid">
                    <section class="panel">
                        <div class="panel__title">
                            <h2>Xu hướng theo giờ</h2>
                            <span class="badge">Live</span>
                        </div>
                        <div id="hourly-trend-chart" class="trend-container"></div>
                    </section>

                    <section class="panel">
                        <div class="panel__title">
                            <h2>Recent Violations</h2>
                            <button class="button button--ghost" type="button" data-nav="/violations">Tất cả</button>
                        </div>
                        <div class="table-container">
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Giờ</th>
                                        <th>Biển số</th>
                                        <th>Camera</th>
                                        <th>Ảnh</th>
                                    </tr>
                                </thead>
                                <tbody id="recent-violations-list">
                                    <tr>
                                        <td colspan="4" class="muted text-center">Đang tải...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </section>
                </div>

                <section class="panel dashboard-cameras">
                    <div class="panel__title">
                        <h2>Camera Quick View</h2>
                        <button class="button button--ghost" type="button" data-nav="/cameras">Mở trang Cameras</button>
                    </div>
                    <div id="dashboardCameraGrid" class="camera-grid"></div>
                </section>
            </div>

            <div id="view-cameras" class="app-view" hidden>
                <section class="hero">
                    <div>
                        <p class="eyebrow">Devices</p>
                        <h2>Cameras</h2>
                        <p class="muted">Danh sách camera realtime. Click card để vào chi tiết camera.</p>
                    </div>
                </section>

                <div id="cameraGrid" class="camera-grid">
                    <div class="muted text-center" style="grid-column: 1 / -1; padding: 2rem;">Đang tải danh sách...</div>
                </div>
            </div>

            <div id="view-camera-detail" class="app-view" hidden>
                <section class="hero">
                    <div>
                        <p class="eyebrow">Camera Detail</p>
                        <h2 id="cameraTitle">Chưa chọn camera</h2>
                        <p id="cameraSubtitle" class="muted">Trang chi tiết camera theo route slug chuẩn.</p>
                    </div>
                    <div class="hero__actions">
                        <button id="toggleOverlayBtn" class="button" type="button">Overlay: ON</button>
                        <button id="reloadLiveBtn" class="button button--secondary" type="button">Tải lại</button>
                    </div>
                </section>

                <div class="detail-grid">
                    <section class="panel detail-main">
                        <div class="panel__title">
                            <h2>Live Stream</h2>
                            <div class="status-row">
                                <span id="onlineBadge" class="badge badge--dim">unknown</span>
                                <span id="streamBadge" class="badge badge--dim">stream unknown</span>
                            </div>
                        </div>
                        <div class="viewer-stage viewer-stage--detail">
                            <img id="streamImage" alt="Live stream">
                            <canvas id="overlayCanvas"></canvas>
                            <div id="viewerEmpty" class="viewer-empty">Chưa có kết nối Camera.</div>
                        </div>
                        <div id="streamWarning" class="notice notice--warning" hidden></div>
                    </section>

                    <aside class="stack detail-side">
                        <section class="panel">
                            <div class="panel__title">
                                <h2>Runtime Panel</h2>
                            </div>
                            <dl class="kv-grid">
                                <div>
                                    <dt>Tín hiệu đèn</dt>
                                    <dd>
                                        <div class="traffic-light-mini" id="trafficLightMini">
                                            <span class="lamp lamp--red" id="lampRed"></span>
                                            <span class="lamp lamp--yellow" id="lampYellow"></span>
                                            <span class="lamp lamp--green" id="lampGreen"></span>
                                        </div>
                                    </dd>
                                </div>
                                <div><dt>Trạng thái</dt><dd id="lightStateText">unknown</dd></div>
                                <div><dt>Phát hiện</dt><dd id="detectionCount">0</dd></div>
                                <div><dt>Khung hình</dt><dd id="frameSize">-</dd></div>
                                <div><dt>Cập nhật</dt><dd id="capturedAt">-</dd></div>
                                <div><dt>IP</dt><dd id="cameraIp">-</dd></div>
                                <div><dt>Stream URL</dt><dd id="cameraStreamUrl">-</dd></div>
                                <div><dt>Worker</dt><dd id="workerState">-</dd></div>
                                <div><dt>Retry</dt><dd id="retryCount">0</dd></div>
                                <div><dt>Last frame</dt><dd id="lastFrameAt">-</dd></div>
                                <div><dt>Last error</dt><dd id="lastError">-</dd></div>
                            </dl>
                        </section>

                        <section class="panel">
                            <div class="panel__title">
                                <h2>Zone Editor</h2>
                                <span id="zoneCount" class="badge">0</span>
                            </div>
                            <div class="tool-list">
                                <span class="tool-chip tool-chip--stop">Stop line</span>
                                <span class="tool-chip tool-chip--violation">Violation zone</span>
                                <span class="tool-chip tool-chip--detect">Detect zone</span>
                                <span class="tool-chip tool-chip--roi">Light ROI</span>
                            </div>
                            <div id="zoneLegend" class="zone-legend"></div>
                        </section>
                    </aside>
                </div>

                <section class="panel">
                    <div class="panel__title">
                        <h2>Recent Violations</h2>
                        <button class="button button--ghost" type="button" id="cameraViolationsNavBtn">Xem tất cả</button>
                    </div>
                    <div class="table-container">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Thời gian</th>
                                    <th>Biển số</th>
                                    <th>Confidence</th>
                                    <th>Ảnh</th>
                                </tr>
                            </thead>
                            <tbody id="cameraRecentViolations">
                                <tr>
                                    <td colspan="4" class="muted text-center">Đang tải...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </section>
            </div>

            <div id="view-violations" class="app-view" hidden>
                <section class="hero">
                    <div>
                        <p class="eyebrow">Events</p>
                        <h2>Violations</h2>
                    </div>
                    <div class="hero__actions">
                        <button id="refreshViolationsBtn" class="button" type="button">Làm mới</button>
                    </div>
                </section>

                <div class="filter-bar panel">
                    <div class="filter-group">
                        <label>Biển số</label>
                        <input type="text" id="filter-plate" placeholder="Biển số xe...">
                    </div>
                    <div class="filter-group">
                        <label>Camera</label>
                        <select id="filter-camera">
                            <option value="">Tất cả</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label>Ngày</label>
                        <input type="date" id="filter-date">
                    </div>
                    <button class="button" type="button" id="applyViolationFiltersBtn">
                        <i class="fa-solid fa-filter"></i>
                    </button>
                </div>

                <section class="panel">
                    <div class="table-container">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Ảnh bằng chứng</th>
                                    <th>Thời gian</th>
                                    <th>Camera</th>
                                    <th>Biển số</th>
                                    <th>Loại</th>
                                    <th>Trạng thái</th>
                                </tr>
                            </thead>
                            <tbody id="violations-list">
                                <tr>
                                    <td colspan="7" class="muted text-center">Đang tải...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </section>
            </div>

            <div id="view-settings" class="app-view" hidden>
                <section class="hero">
                    <div>
                        <p class="eyebrow">Config</p>
                        <h2>Settings</h2>
                        <p class="muted">Frontend chỉ hiển thị config hệ thống lấy từ backend/.env và backend API.</p>
                    </div>
                </section>

                <div class="settings-grid">
                    <section class="panel">
                        <div class="panel__title">
                            <h2>Frontend</h2>
                        </div>
                        <dl class="kv-grid">
                            <div><dt>Current path</dt><dd id="settingsCurrentPath">-</dd></div>
                            <div><dt>API root</dt><dd id="settingsApiRoot">-</dd></div>
                            <div><dt>Refresh interval</dt><dd id="settingsRefreshInterval">-</dd></div>
                        </dl>
                    </section>

                    <section class="panel">
                        <div class="panel__title">
                            <h2>Routing</h2>
                        </div>
                        <div class="route-list">
                            <code>/dashboard</code>
                            <code>/cameras</code>
                            <code>/cameras/:cameraId-:slug</code>
                            <code>/violations</code>
                            <code>/settings</code>
                        </div>
                    </section>
                </div>
            </div>
        </main>
    </div>

    <div id="evidenceModal" class="modal" hidden>
        <div class="modal__content panel">
            <div class="panel__title">
                <h2>Chi tiết vi phạm</h2>
                <button class="button button--ghost" type="button" id="closeEvidenceModalBtn">&times;</button>
            </div>
            <div class="evidence-gallery">
                <div class="evidence-item">
                    <p class="muted">Toàn cảnh</p>
                    <img id="modalFullImage" src="" alt="Full view">
                </div>
                <div class="evidence-item">
                    <p class="muted">Biển số</p>
                    <img id="modalPlateImage" src="" alt="Plate view">
                </div>
            </div>
            <div id="modalDetails" class="modal-info kv-grid"></div>
        </div>
    </div>

    <script src="/assets/js/App.js" defer></script>
</body>

</html>
