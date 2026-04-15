(function () {
  "use strict";

  const TOKEN_KEY = "TRAFFIC_AI_TOKEN";
  const REMEMBER_KEY = "TRAFFIC_AI_REMEMBER";
  const LOCKOUT_KEY = "TRAFFIC_AI_LOCKOUT";
  const MAX_ATTEMPTS = 5;
  const LOCKOUT_MS = 30_000;
  const REQUEST_TIMEOUT = 8_000;

  const form = document.getElementById("loginForm");
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const loginBtn = document.getElementById("loginBtn");
  const errorBox = document.getElementById("errorBox");
  const togglePwBtn = document.getElementById("togglePw");
  const rememberMe = document.getElementById("rememberMe");

  const statusEls = {
    serverPill: document.getElementById("serverPill"),
    serverPillTxt: document.getElementById("serverPillTxt"),
    modeBadge: document.getElementById("modeBadge"),
    modeBadgeTxt: document.getElementById("modeBadgeTxt"),
    serverStatusBar: document.getElementById("serverStatusBar"),
    serverBarTxt: document.getElementById("serverBarTxt"),
    chipEsp32: document.getElementById("chipEsp32"),
    chipEsp32Val: document.getElementById("chipEsp32Val"),
    chipMqtt: document.getElementById("chipMqtt"),
    chipMqttVal: document.getElementById("chipMqttVal"),
    chipCam: document.getElementById("chipCam"),
    chipCamVal: document.getElementById("chipCamVal")
  };

  if (!form) return;

  function resolveRoute(routeName) {
    const isStaticPage = window.location.protocol === "file:" || /\.html?$/i.test(window.location.pathname);
    return isStaticPage ? routeName + ".html" : "/" + routeName;
  }

  function redirectTo(routeName) {
    window.location.replace(resolveRoute(routeName));
  }

  function setPill(state, text) {
    if (statusEls.serverPill) statusEls.serverPill.className = `status-pill status-pill-${state}`;
    if (statusEls.serverPillTxt) statusEls.serverPillTxt.textContent = text;
  }

  function setMode(state, text) {
    if (statusEls.modeBadge) statusEls.modeBadge.className = `mode-badge mode-badge-${state}`;
    if (statusEls.modeBadgeTxt) statusEls.modeBadgeTxt.textContent = text;
  }

  function setServerBar(state, text) {
    if (statusEls.serverStatusBar) statusEls.serverStatusBar.className = `server-status-bar server-status-bar-${state}`;
    if (statusEls.serverBarTxt) statusEls.serverBarTxt.textContent = text;
  }

  function setChip(target, state, label) {
    const chip = statusEls[target];
    const value = statusEls[`${target}Val`];
    if (chip) chip.className = `device-chip device-chip-${state}`;
    if (value) value.textContent = label;
  }

  function showError(message) {
    if (!errorBox) return;
    if (!message) {
      errorBox.textContent = "";
      errorBox.classList.remove("visible");
      return;
    }
    errorBox.textContent = message;
    errorBox.classList.add("visible");
  }

  function clearFieldErrors() {
    ["fieldUsername", "fieldPassword"].forEach((id) => {
      const field = document.getElementById(id);
      if (!field) return;
      field.classList.remove("has-error", "error");
      const err = field.querySelector(".field__err");
      if (err) err.textContent = "";
    });
  }

  function setFieldError(fieldId, message) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    field.classList.add("has-error", "error");
    const err = field.querySelector(".field__err");
    if (err) err.textContent = message;
  }

  function validateInputs(username, password) {
    clearFieldErrors();
    let ok = true;
    if (!username || username.length < 2) {
      setFieldError("fieldUsername", "Username là bắt buộc.");
      ok = false;
    }
    if (!password || password.length < 4) {
      setFieldError("fieldPassword", "Password là bắt buộc.");
      ok = false;
    }
    return ok;
  }

  function setLoading(active, locked = false) {
    if (!loginBtn) return;
    loginBtn.disabled = active;
    loginBtn.classList.toggle("loading", active && !locked);
    loginBtn.classList.toggle("locked", locked);
    const text = loginBtn.querySelector(".btn-submit__text");
    if (!text) return;
    if (locked) {
      return;
    }
    text.textContent = active ? "Đang xác thực..." : "Đăng nhập";
  }

  function getLockoutState() {
    try {
      const raw = sessionStorage.getItem(LOCKOUT_KEY);
      return raw ? JSON.parse(raw) : { attempts: 0, lockedUntil: 0 };
    } catch (_) {
      return { attempts: 0, lockedUntil: 0 };
    }
  }

  function setLockoutState(state) {
    sessionStorage.setItem(LOCKOUT_KEY, JSON.stringify(state));
  }

  function isLockedOut() {
    return Date.now() < getLockoutState().lockedUntil;
  }

  function remainingLockout() {
    return Math.max(0, Math.ceil((getLockoutState().lockedUntil - Date.now()) / 1000));
  }

  function recordFailedAttempt() {
    const state = getLockoutState();
    state.attempts = (state.attempts || 0) + 1;
    if (state.attempts >= MAX_ATTEMPTS) {
      state.lockedUntil = Date.now() + LOCKOUT_MS;
      state.attempts = 0;
    }
    setLockoutState(state);
  }

  function resetAttempts() {
    setLockoutState({ attempts: 0, lockedUntil: 0 });
  }

  let lockoutTimer = null;
  function startLockoutCountdown() {
    clearInterval(lockoutTimer);
    setLoading(true, true);
    const text = loginBtn.querySelector(".btn-submit__text");

    const tick = () => {
      const secs = remainingLockout();
      if (secs <= 0) {
        clearInterval(lockoutTimer);
        lockoutTimer = null;
        setLoading(false);
        if (text) text.textContent = "Đăng nhập";
        showError("");
        return;
      }
      if (text) text.textContent = `Khóa (${secs}s)`;
      showError(`Quá nhiều lần thử. Vui lòng thử lại sau ${secs}s.`);
    };

    tick();
    lockoutTimer = setInterval(tick, 1000);
  }

  function saveSession(token, username) {
    localStorage.setItem(TOKEN_KEY, token);
    if (rememberMe && rememberMe.checked) {
      localStorage.setItem(REMEMBER_KEY, JSON.stringify({ username }));
    } else {
      localStorage.removeItem(REMEMBER_KEY);
    }
  }

  function restoreRememberedUser() {
    try {
      const raw = localStorage.getItem(REMEMBER_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed.username && usernameInput) {
        usernameInput.value = parsed.username;
        if (rememberMe) rememberMe.checked = true;
      }
    } catch (_) {
      localStorage.removeItem(REMEMBER_KEY);
    }
  }

  async function apiAuth(username, password) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal
      });

      const data = await response.json().catch(() => null);
      if (!response.ok || !data || !data.ok || !data.token) {
        return { error: data?.error || `Không thể đăng nhập (${response.status}).` };
      }
      return { token: data.token };
    } catch (error) {
      if (error?.name === "AbortError") {
        return { error: "Yêu cầu đăng nhập bị timeout." };
      }
      return { error: "Không thể kết nối backend xác thực." };
    } finally {
      clearTimeout(timer);
    }
  }

  async function refreshRuntimeStatus() {
    setPill("checking", "Đang kiểm tra backend");
    setMode("checking", "Checking");
    setServerBar("checking", "Đang kết nối backend xác thực...");
    setChip("chipEsp32", "checking", "...");
    setChip("chipMqtt", "checking", "...");
    setChip("chipCam", "checking", "...");

    try {
      const healthResponse = await fetch("/api/health");
      const health = await healthResponse.json();
      if (!healthResponse.ok || !health?.ok) {
        throw new Error("health");
      }

      setPill("online", "Backend online");
      setServerBar("online", `Backend sẵn sàng xác thực • v${health.version || "runtime"}`);
      setChip("chipMqtt", health.mqtt ? "online" : "offline", health.mqtt ? "ONLINE" : "OFFLINE");

      try {
        const token = localStorage.getItem(TOKEN_KEY) || "TRAFFIC_AI_TOKEN";
        const bootstrapResponse = await fetch("/api/bootstrap", {
          headers: { Authorization: `Bearer ${token}` }
        });
        const bootstrap = await bootstrapResponse.json();
        const devices = bootstrap?.devices || {};
        const runtimeOnline = Object.values(devices).some((device) => device?.status === "ONLINE");
        const cameraOnline = Object.values(devices).some((device) => String(device?.name || "").toLowerCase().includes("cam") && device?.status === "ONLINE");

        setChip("chipEsp32", runtimeOnline ? "online" : "offline", runtimeOnline ? "ONLINE" : "OFFLINE");
        setChip("chipCam", cameraOnline ? "online" : "offline", cameraOnline ? "ONLINE" : "OFFLINE");
        if (runtimeOnline) {
          setMode("live", "Live runtime");
        } else {
          setMode("ready", "Backend ready");
        }
      } catch (_) {
        setChip("chipEsp32", "offline", "OFFLINE");
        setChip("chipCam", "offline", "OFFLINE");
        setMode("ready", "Backend ready");
      }
    } catch (_) {
      setPill("offline", "Backend offline");
      setMode("auto", "Offline");
      setServerBar("offline", "Không thể kết nối backend xác thực.");
      setChip("chipEsp32", "offline", "OFFLINE");
      setChip("chipMqtt", "offline", "OFFLINE");
      setChip("chipCam", "offline", "OFFLINE");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isLockedOut()) {
      startLockoutCountdown();
      return;
    }

    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!validateInputs(username, password)) return;

    showError("");
    setLoading(true);

    const result = await apiAuth(username, password);
    if (result.error) {
      recordFailedAttempt();
      setLoading(false);
      if (isLockedOut()) {
        startLockoutCountdown();
        return;
      }
      const remaining = MAX_ATTEMPTS - getLockoutState().attempts;
      showError(`${result.error}${remaining > 0 ? ` (${remaining} lần còn lại)` : ""}`);
      return;
    }

    resetAttempts();
    saveSession(result.token, username);
    const label = loginBtn.querySelector(".btn-submit__text");
    if (label) label.textContent = "Đang chuyển hướng...";
    redirectTo("main");
  });

  [usernameInput, passwordInput].forEach((input) => {
    input?.addEventListener("input", () => {
      clearFieldErrors();
      showError("");
    });
  });

  togglePwBtn?.addEventListener("click", () => {
    const isHidden = passwordInput.type === "password";
    passwordInput.type = isHidden ? "text" : "password";
    const open = togglePwBtn.querySelector(".eye-open");
    const closed = togglePwBtn.querySelector(".eye-closed");
    if (open) open.style.display = isHidden ? "none" : "inline";
    if (closed) closed.style.display = isHidden ? "inline" : "none";
  });

  restoreRememberedUser();
  refreshRuntimeStatus();

  if (isLockedOut()) {
    startLockoutCountdown();
  }
})();
