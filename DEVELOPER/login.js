/**
 * TrafficAI — Login Controller v5.0 ULTRA PREMIUM
 * login.js  |  Neural Authentication Module
 *
 * Giữ nguyên toàn bộ logic v4.0 (gốc):
 *  - Standard credential login  (/api/login)
 *  - Legacy fallback credentials
 *  - Remember-me via localStorage
 *  - Field-level validation
 *  - Abort controller / 8s timeout
 *  - Brute-force lockout (5 attempts → 30s)
 *  - Countdown timer UI
 *  - Particles.js animated background
 *  - Shake animation
 *
 * Nâng cấp v5.0 MỚI:
 *  - 3D card tilt với gyroscope mobile support
 *  - Glow border trace (conic-gradient)
 *  - Parallax background layers
 *  - Magnetic submit button
 *  - Typing character counter & strength meter
 *  - Sound feedback (Web Audio API — optional)
 *  - Custom cursor
 *  - Advanced particle config
 *  - Boot sequence với session check
 *  - Real/sim mode detection từ sessionStorage
 */

(function () {
  "use strict";

  /* ════════════════════════════════════════════
     CONSTANTS
  ════════════════════════════════════════════ */
  const TOKEN_KEY       = "TRAFFIC_AI_TOKEN";
  const REMEMBER_KEY    = "TRAFFIC_AI_REMEMBER";
  const LOCKOUT_KEY     = "TRAFFIC_AI_LOCKOUT";
  const BOOT_STATE_KEY  = "TRAFFIC_BOOT_STATE";
  const MAX_ATTEMPTS    = 5;
  const LOCKOUT_MS      = 30_000;
  const REQUEST_TIMEOUT = 8_000;

  /* Legacy / offline fallback credentials */
  const LEGACY_USERS = [
    { username: "admin",   password: "admin123",  role: "superadmin" },
    { username: "analyst", password: "analyst123", role: "analyst"   },
  ];

  /* ════════════════════════════════════════════
     DOM REFERENCES
  ════════════════════════════════════════════ */
  const form          = document.getElementById("loginForm");
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const loginBtn      = document.getElementById("loginBtn");
  const errorBox      = document.getElementById("errorBox");
  const togglePwBtn   = document.getElementById("togglePw");
  const rememberMe    = document.getElementById("rememberMe");

  if (!form) return; // Guard: không phải trang login

  /* ════════════════════════════════════════════
     1. REMEMBER-ME — restore saved username
  ════════════════════════════════════════════ */
  (function restoreRemember() {
    try {
      const saved = localStorage.getItem(REMEMBER_KEY);
      if (saved) {
        const { username } = JSON.parse(saved);
        if (username && usernameInput) {
          usernameInput.value = username;
          if (rememberMe) rememberMe.checked = true;
        }
      }
    } catch (_) { /* ignore */ }
  })();

  /* ════════════════════════════════════════════
     2. LOCKOUT GUARD
  ════════════════════════════════════════════ */
  function getLockoutState() {
    try {
      const raw = sessionStorage.getItem(LOCKOUT_KEY);
      return raw ? JSON.parse(raw) : { attempts: 0, lockedUntil: 0 };
    } catch (_) { return { attempts: 0, lockedUntil: 0 }; }
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

  /* Lockout countdown timer */
  let lockoutTimer = null;

  function startLockoutCountdown() {
    clearInterval(lockoutTimer);
    loginBtn.disabled = true;
    loginBtn.classList.remove("loading");

    const textEl    = loginBtn.querySelector(".btn-submit__text, .text");
    const spinnerEl = loginBtn.querySelector(".btn-submit__spinner, .spinner");
    const arrowEl   = loginBtn.querySelector(".btn-submit__arrow");

    if (spinnerEl) spinnerEl.style.display = "none";
    if (arrowEl)   arrowEl.style.display   = "none";

    /* Add locked class for CSS */
    loginBtn.classList.add("locked");

    lockoutTimer = setInterval(() => {
      const secs = remainingLockout();
      if (secs <= 0) {
        clearInterval(lockoutTimer);
        lockoutTimer = null;
        loginBtn.disabled = false;
        loginBtn.classList.remove("locked");
        if (textEl) textEl.textContent = "Authenticate";
        if (arrowEl) { arrowEl.style.display = ""; }
        showError("");
        return;
      }
      if (textEl) textEl.textContent = `Locked (${secs}s)`;
      showError(`Quá nhiều lần thử. Vui lòng thử lại sau ${secs}s.`);
    }, 1000);

    const secs = remainingLockout();
    if (textEl) textEl.textContent = `Locked (${secs}s)`;
    showError(`Quá nhiều lần thử. Vui lòng thử lại sau ${secs}s.`);
  }

  /* ════════════════════════════════════════════
     3. UI HELPERS
  ════════════════════════════════════════════ */
  function setLoading(active, locked = false) {
    loginBtn.disabled = active;
    if (active && !locked) {
      loginBtn.classList.add("loading");
    } else {
      loginBtn.classList.remove("loading");
      if (!locked) {
        loginBtn.innerHTML = `
          <span class="btn-submit__text text">Authenticate</span>
          <span class="btn-submit__spinner spinner"></span>
          <svg class="btn-submit__arrow" viewBox="0 0 20 20" fill="none">
            <path d="M4 10h12M12 6l4 4-4 4" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
          </svg>`;
        /* Re-bind magnetic button after innerHTML rebuild */
        initMagneticBtn();
      }
    }
  }

  function showError(msg) {
    if (!errorBox) return;
    if (msg) {
      errorBox.textContent = msg;
      errorBox.classList.add("visible");
      playErrorSound();
    } else {
      errorBox.textContent = "";
      errorBox.classList.remove("visible");
    }
  }

  function clearFieldErrors() {
    ["fieldUsername", "fieldPassword"].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.classList.remove("has-error", "error");
      const err = el.querySelector(".field__err");
      if (err) err.textContent = "";
    });
  }

  function setFieldError(fieldId, msg) {
    const el = document.getElementById(fieldId);
    if (!el) return;
    el.classList.add("has-error", "error");
    const err = el.querySelector(".field__err");
    if (err) err.textContent = msg;
  }

  function validateInputs(username, password) {
    let valid = true;
    clearFieldErrors();
    if (!username || username.length < 2) {
      setFieldError("fieldUsername", "Username is required.");
      valid = false;
    }
    if (!password || password.length < 4) {
      setFieldError("fieldPassword", "Password is required.");
      valid = false;
    }
    return valid;
  }

  /* ════════════════════════════════════════════
     4. SAVE / CLEAR SESSION
  ════════════════════════════════════════════ */
  function saveSession(token, username) {
    localStorage.setItem(TOKEN_KEY, token);
    if (rememberMe && rememberMe.checked) {
      localStorage.setItem(REMEMBER_KEY, JSON.stringify({ username }));
    } else {
      localStorage.removeItem(REMEMBER_KEY);
    }
  }

  /* ════════════════════════════════════════════
     5. LEGACY FALLBACK AUTH
  ════════════════════════════════════════════ */
  function legacyAuth(username, password) {
    const user = LEGACY_USERS.find(
      u => u.username === username && u.password === password
    );
    if (!user) return null;
    const ts  = Date.now();
    const raw = `${user.username}:${user.role}:${ts}`;
    return { token: `legacy.${btoa(raw)}`, role: user.role };
  }

  /* ════════════════════════════════════════════
     6. PRIMARY AUTH — /api/login
  ════════════════════════════════════════════ */
  async function apiAuth(username, password) {
    const controller = new AbortController();
    const timeout    = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      const ct = response.headers.get("content-type") || "";
      if (!ct.includes("application/json")) return { useLegacy: true };

      const data = await response.json().catch(() => ({}));

      if (!response.ok || !data.ok) {
        const msg = data.error || (response.status === 401
          ? "Invalid credentials."
          : `Server error (${response.status}).`);
        return { error: msg };
      }

      if (!data.token) return { error: "Invalid server response. Missing token." };

      return { token: data.token, role: data.role || "operator" };

    } catch (err) {
      clearTimeout(timeout);
      if (err.name === "AbortError")  return { error: "Request timed out. Check your connection." };
      if (err.name === "TypeError")   return { useLegacy: true };
      return { error: err.message || "An unexpected error occurred." };
    }
  }

  /* ════════════════════════════════════════════
     7. SHAKE ANIMATION (giữ từ v4.0)
  ════════════════════════════════════════════ */
  function shakeCard() {
    const card = document.querySelector(".card, .login-card");
    if (!card) return;
    card.style.animation = "none";
    card.offsetHeight; // force reflow
    card.style.animation = "shake .42s ease";
    setTimeout(() => { card.style.animation = ""; }, 450);
  }

  /* Inject shake keyframe nếu chưa có */
  if (!document.getElementById("__shake_kf__") && !document.getElementById("shake-style")) {
    const style = document.createElement("style");
    style.id = "__shake_kf__";
    style.textContent = `
      @keyframes shake {
        0%,100% { transform: translateX(0) rotateY(0); }
        20%      { transform: translateX(-9px) rotateY(-2deg); }
        40%      { transform: translateX(9px)  rotateY(2deg); }
        60%      { transform: translateX(-6px) rotateY(-1.5deg); }
        80%      { transform: translateX(6px)  rotateY(1.5deg); }
      }`;
    document.head.appendChild(style);
  }

  /* ════════════════════════════════════════════
     8. FORM SUBMIT HANDLER
  ════════════════════════════════════════════ */
  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    if (isLockedOut()) {
      startLockoutCountdown();
      return;
    }

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!validateInputs(username, password)) return;

    showError("");
    setLoading(true);

    let result = await apiAuth(username, password);

    if (result.useLegacy) {
      const legacy = legacyAuth(username, password);
      result = legacy ? legacy : { error: "Invalid credentials." };
    }

    /* ── Handle failure ── */
    if (result.error) {
      recordFailedAttempt();
      setLoading(false);

      if (isLockedOut()) {
        startLockoutCountdown();
        return;
      }

      const { attempts } = getLockoutState();
      const remaining    = MAX_ATTEMPTS - attempts;
      const suffix = remaining > 0
        ? ` (${remaining} attempt${remaining !== 1 ? "s" : ""} remaining)`
        : "";

      showError(result.error + suffix);
      shakeCard();
      playErrorSound();
      return;
    }

    /* ── SUCCESS ── */
    resetAttempts();
    saveSession(result.token, username);

    /* Visual success feedback */
    const textEl    = loginBtn.querySelector(".btn-submit__text, .text");
    const spinnerEl = loginBtn.querySelector(".btn-submit__spinner, .spinner");
    const arrowEl   = loginBtn.querySelector(".btn-submit__arrow");

    if (spinnerEl) spinnerEl.style.display = "none";
    if (arrowEl)   arrowEl.style.display   = "none";
    if (textEl)    textEl.textContent       = "✓ Access Granted";
    if (textEl)    textEl.style.opacity     = "1";

    loginBtn.style.background = "linear-gradient(90deg, #00ff9d, #00e5ff)";
    loginBtn.style.boxShadow  = "0 0 40px rgba(0,255,157,0.55), 0 0 80px rgba(0,229,255,0.2)";
    loginBtn.style.color      = "#000";

    playSuccessSound();

    /* Success flash overlay */
    const flash = document.createElement("div");
    flash.style.cssText = `
      position:fixed;inset:0;background:rgba(0,245,212,0.06);
      z-index:9999;pointer-events:none;
      animation:flashIn .4s ease forwards;`;
    document.body.appendChild(flash);
    setTimeout(() => flash.remove(), 500);

    setTimeout(() => {
      window.location.replace("main.html");
    }, 820);
  });

  /* ════════════════════════════════════════════
     9. PASSWORD TOGGLE (giữ từ v4.0)
  ════════════════════════════════════════════ */
  if (togglePwBtn) {
    togglePwBtn.addEventListener("click", function () {
      const isPassword = passwordInput.type === "password";
      passwordInput.type = isPassword ? "text" : "password";

      const eyeOpen   = togglePwBtn.querySelector(".eye-open, .eye-open-svg");
      const eyeClosed = togglePwBtn.querySelector(".eye-closed, .eye-closed-svg");

      if (eyeOpen)   eyeOpen.style.display   = isPassword ? "none" : "";
      if (eyeClosed) eyeClosed.style.display = isPassword ? ""     : "none";

      passwordInput.focus();
    });
  }

  /* ════════════════════════════════════════════
     10. CLEAR FIELD ERROR ON TYPING (giữ từ v4.0)
  ════════════════════════════════════════════ */
  [usernameInput, passwordInput].forEach(input => {
    if (!input) return;
    input.addEventListener("input", function () {
      const fieldId = this.id === "username" ? "fieldUsername" : "fieldPassword";
      const el = document.getElementById(fieldId);
      if (el) {
        el.classList.remove("has-error", "error");
        const err = el.querySelector(".field__err");
        if (err) err.textContent = "";
      }
      showError("");
    });
  });

  /* ════════════════════════════════════════════
     11. PASSWORD STRENGTH METER (v5.0 MỚI)
     Hiển thị strength khi user gõ password
  ════════════════════════════════════════════ */
  (function initPasswordStrength() {
    if (!passwordInput) return;

    /* Tạo strength bar */
    const wrap = passwordInput.closest(".field, .field-group");
    if (!wrap) return;

    const strengthBar = document.createElement("div");
    strengthBar.className = "pw-strength";
    strengthBar.innerHTML = `
      <div class="pw-strength__bar">
        <div class="pw-strength__fill" id="pwStrengthFill"></div>
      </div>
      <span class="pw-strength__label" id="pwStrengthLabel"></span>`;

    /* Chèn sau field__input-wrap */
    const inputWrap = wrap.querySelector(".field__input-wrap, .password-wrapper");
    if (inputWrap) inputWrap.after(strengthBar);

    /* Inject strength CSS nếu chưa có */
    if (!document.getElementById("__pw_strength_css__")) {
      const s = document.createElement("style");
      s.id = "__pw_strength_css__";
      s.textContent = `
        .pw-strength {
          display: flex; align-items: center; gap: 8px;
          opacity: 0; transition: opacity 0.3s ease;
          margin-top: -4px;
        }
        .pw-strength.visible { opacity: 1; }
        .pw-strength__bar {
          flex: 1; height: 3px;
          background: rgba(255,255,255,0.08);
          border-radius: 99px; overflow: hidden;
        }
        .pw-strength__fill {
          height: 100%; width: 0%;
          border-radius: 99px;
          transition: width 0.4s cubic-bezier(.4,0,.2,1), background 0.4s ease;
        }
        .pw-strength__label {
          font-family: 'JetBrains Mono', monospace;
          font-size: 9px; letter-spacing: 1px;
          text-transform: uppercase; min-width: 48px;
          text-align: right;
          transition: color 0.3s ease;
        }
        .pw-s-weak   .pw-strength__fill { width: 25%; background: #ff3860; }
        .pw-s-fair   .pw-strength__fill { width: 50%; background: #ffb020; }
        .pw-s-good   .pw-strength__fill { width: 75%; background: #00e5ff; }
        .pw-s-strong .pw-strength__fill { width: 100%; background: #00e87a; }
        .pw-s-weak   .pw-strength__label { color: #ff3860; content: 'WEAK'; }
        .pw-s-fair   .pw-strength__label { color: #ffb020; }
        .pw-s-good   .pw-strength__label { color: #00e5ff; }
        .pw-s-strong .pw-strength__label { color: #00e87a; }
        .error-box.visible {
          display: block !important;
          animation: errFadeIn 0.25s ease both;
        }
        @keyframes errFadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes flashIn {
          from { opacity: 0; }
          50%  { opacity: 1; }
          to   { opacity: 0; }
        }
        .btn-submit.locked {
          background: linear-gradient(90deg, #2a1a2a, #1a1a2a) !important;
          color: rgba(255,255,255,0.4) !important;
          cursor: not-allowed !important;
        }`;
      document.head.appendChild(s);
    }

    function getStrength(pw) {
      if (!pw || pw.length < 4) return { level: 0, label: "" };
      let score = 0;
      if (pw.length >= 8)  score++;
      if (pw.length >= 12) score++;
      if (/[A-Z]/.test(pw)) score++;
      if (/[0-9]/.test(pw)) score++;
      if (/[^A-Za-z0-9]/.test(pw)) score++;
      if (score <= 1) return { level: 1, label: "WEAK" };
      if (score === 2) return { level: 2, label: "FAIR" };
      if (score === 3) return { level: 3, label: "GOOD" };
      return { level: 4, label: "STRONG" };
    }

    const levelClass = ["", "pw-s-weak", "pw-s-fair", "pw-s-good", "pw-s-strong"];

    passwordInput.addEventListener("input", function () {
      const val    = this.value;
      const result = getStrength(val);
      const label  = document.getElementById("pwStrengthLabel");

      strengthBar.classList.remove("pw-s-weak", "pw-s-fair", "pw-s-good", "pw-s-strong");

      if (!val) {
        strengthBar.classList.remove("visible");
        return;
      }

      strengthBar.classList.add("visible");
      if (result.level > 0) {
        strengthBar.classList.add(levelClass[result.level]);
        if (label) label.textContent = result.label;
      }
    });
  })();

  /* ════════════════════════════════════════════
     12. 3D CARD TILT (v5.0 MỚI)
     CSS classes từ login.css: .tilt-active, .tilt-enter,
     .tilt-parallax, .glow-border
  ════════════════════════════════════════════ */
  (function initCardTilt() {
    const card     = document.querySelector(".card, .login-card");
    const branding = document.querySelector(".panel__inner, .branding");
    if (!card) return;

    /* Inject glow border div nếu chưa có */
    if (!card.querySelector(".glow-border")) {
      const gb = document.createElement("div");
      gb.className = "glow-border";
      card.prepend(gb);
    }

    const TILT_MAX    = 10;     /* degrees */
    const TILT_SCALE  = 1.015;
    const BG_PARALLAX = 14;     /* px range for background parallax */

    let rafId = null;
    let currentTilt = { rx: 0, ry: 0 };
    let targetTilt  = { rx: 0, ry: 0 };

    /* Lấy panel right để track mouse */
    const panel = card.closest(".panel, .panel--right, .right-panel") || document.body;

    function lerp(a, b, t) { return a + (b - a) * t; }

    function applyTilt() {
      currentTilt.rx = lerp(currentTilt.rx, targetTilt.rx, 0.1);
      currentTilt.ry = lerp(currentTilt.ry, targetTilt.ry, 0.1);

      const { rx, ry } = currentTilt;

      /* Card 3D transform */
      card.style.transform = `
        perspective(900px)
        rotateX(${rx}deg)
        rotateY(${ry}deg)
        scale(${TILT_SCALE})`;

      /* Shadow shift — simulates real light source */
      const shadowX = ry * 2.5;
      const shadowY = -rx * 2.5 + 22;
      card.style.setProperty("--shadow-x", `${shadowX}px`);
      card.style.setProperty("--shadow-y", `${shadowY}px`);

      /* Background parallax */
      const bx = -ry * 0.8;
      const by = rx  * 0.8;
      document.documentElement.style.setProperty("--bx", `${bx}px`);
      document.documentElement.style.setProperty("--by", `${by}px`);

      /* Branding parallax */
      if (branding) {
        branding.style.transform = `perspective(1200px) rotateX(${rx * 0.3}deg) rotateY(${ry * 0.4}deg)`;
        branding.classList.add("tilt-parallax");
      }

      rafId = requestAnimationFrame(applyTilt);
    }

    panel.addEventListener("mousemove", function (e) {
      const rect   = panel.getBoundingClientRect();
      const cx     = rect.left + rect.width  / 2;
      const cy     = rect.top  + rect.height / 2;
      const dx     = (e.clientX - cx) / (rect.width  / 2);
      const dy     = (e.clientY - cy) / (rect.height / 2);

      targetTilt.rx = -dy * TILT_MAX;
      targetTilt.ry =  dx * TILT_MAX;

      card.classList.add("tilt-active");
      if (!rafId) applyTilt();
    });

    panel.addEventListener("mouseleave", function () {
      targetTilt.rx = 0;
      targetTilt.ry = 0;
      card.classList.remove("tilt-active");
      if (branding) branding.classList.remove("tilt-parallax");
      document.documentElement.style.setProperty("--bx", "0px");
      document.documentElement.style.setProperty("--by", "0px");
    });

    /* Sheen on mouse enter */
    panel.addEventListener("mouseenter", function () {
      card.classList.add("tilt-enter");
      setTimeout(() => card.classList.remove("tilt-enter"), 600);
    });

    /* Mobile: Gyroscope tilt */
    if (window.DeviceOrientationEvent) {
      window.addEventListener("deviceorientation", function (e) {
        if (e.beta === null || e.gamma === null) return;
        const rx = Math.max(-TILT_MAX, Math.min(TILT_MAX, e.beta  * 0.3));
        const ry = Math.max(-TILT_MAX, Math.min(TILT_MAX, e.gamma * 0.3));
        targetTilt.rx = rx;
        targetTilt.ry = ry;
        if (!rafId) applyTilt();
      });
    }
  })();

  /* ════════════════════════════════════════════
     13. MAGNETIC SUBMIT BUTTON (v5.0 MỚI)
  ════════════════════════════════════════════ */
  function initMagneticBtn() {
    const btn = document.querySelector(".btn-submit, .submit-btn");
    if (!btn) return;

    btn.addEventListener("mousemove", function (e) {
      if (this.disabled) return;
      const rect = this.getBoundingClientRect();
      const dx   = e.clientX - (rect.left + rect.width  / 2);
      const dy   = e.clientY - (rect.top  + rect.height / 2);
      this.style.transform = `translate(${dx * 0.18}px, ${dy * 0.18}px) scale(1.03)`;
    });

    btn.addEventListener("mouseleave", function () {
      this.style.transform = "";
    });
  }

  initMagneticBtn();

  /* ════════════════════════════════════════════
     14. CUSTOM CURSOR (v5.0 MỚI)
  ════════════════════════════════════════════ */
  (function initCursor() {
    /* Inject cursor elements nếu chưa có */
    if (document.getElementById("__cursor__")) return;

    const cursorEl = document.createElement("div");
    cursorEl.id = "__cursor__";
    cursorEl.style.cssText = `
      position:fixed;width:8px;height:8px;border-radius:50%;
      background:#00f5d4;pointer-events:none;z-index:9999;
      transform:translate(-50%,-50%);
      box-shadow:0 0 10px #00f5d4,0 0 22px rgba(0,245,212,0.3);
      transition:background 0.2s ease;`;

    const ringEl = document.createElement("div");
    ringEl.id = "__cursor_ring__";
    ringEl.style.cssText = `
      position:fixed;width:28px;height:28px;border-radius:50%;
      border:1px solid rgba(0,245,212,0.4);pointer-events:none;z-index:9998;
      transform:translate(-50%,-50%);
      transition:width 0.2s ease,height 0.2s ease;`;

    document.body.appendChild(cursorEl);
    document.body.appendChild(ringEl);

    let mx = -100, my = -100;
    let rx = -100, ry = -100;

    document.addEventListener("mousemove", e => {
      mx = e.clientX; my = e.clientY;
      cursorEl.style.left = mx + "px";
      cursorEl.style.top  = my + "px";
    });

    function animRing() {
      rx += (mx - rx) * 0.16;
      ry += (my - ry) * 0.16;
      ringEl.style.left = rx + "px";
      ringEl.style.top  = ry + "px";
      requestAnimationFrame(animRing);
    }
    animRing();

    /* Grow ring on interactive elements */
    document.querySelectorAll("button, a, input, label").forEach(el => {
      el.addEventListener("mouseenter", () => {
        ringEl.style.width  = "48px";
        ringEl.style.height = "48px";
        ringEl.style.borderColor = "rgba(0,245,212,0.7)";
        cursorEl.style.background = "#00e5ff";
      });
      el.addEventListener("mouseleave", () => {
        ringEl.style.width  = "28px";
        ringEl.style.height = "28px";
        ringEl.style.borderColor = "rgba(0,245,212,0.4)";
        cursorEl.style.background = "#00f5d4";
      });
    });

    /* Hide cursor on touch */
    document.addEventListener("touchstart", () => {
      cursorEl.style.display = "none";
      ringEl.style.display   = "none";
    }, { once: true });
  })();

  /* ════════════════════════════════════════════
     15. WEB AUDIO — Sound feedback (v5.0 MỚI)
     Optional — graceful degradation nếu không hỗ trợ
  ════════════════════════════════════════════ */
  let audioCtx = null;

  function getAudioCtx() {
    if (!audioCtx) {
      try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
      catch (_) { return null; }
    }
    return audioCtx;
  }

  function playTone(freq, type, duration, gain = 0.06) {
    const ctx = getAudioCtx();
    if (!ctx) return;
    try {
      const osc = ctx.createOscillator();
      const g   = ctx.createGain();
      osc.connect(g);
      g.connect(ctx.destination);
      osc.type      = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      g.gain.setValueAtTime(gain, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration);
    } catch (_) { /* ignore */ }
  }

  function playErrorSound() {
    playTone(180, "sawtooth", 0.18, 0.05);
    setTimeout(() => playTone(140, "sawtooth", 0.22, 0.04), 100);
  }

  function playSuccessSound() {
    playTone(523, "sine", 0.12, 0.06);
    setTimeout(() => playTone(659, "sine", 0.12, 0.06), 80);
    setTimeout(() => playTone(784, "sine", 0.18, 0.07), 160);
  }

  function playKeySound() {
    playTone(880, "sine", 0.04, 0.018);
  }

  /* Subtle key sound on typing */
  [usernameInput, passwordInput].forEach(inp => {
    if (!inp) return;
    inp.addEventListener("keydown", playKeySound);
  });

  /* ════════════════════════════════════════════
     16. PARTICLES.JS (giữ từ v4.0, nâng cấp config)
  ════════════════════════════════════════════ */
  (function initParticles() {
    if (typeof particlesJS === "undefined") return;

    particlesJS("particles", {
      particles: {
        number: { value: 60, density: { enable: true, value_area: 900 } },
        color:  { value: ["#00e5ff", "#00f5d4", "#0077ff"] },
        shape:  { type: "circle" },
        opacity: {
          value: 0.32,
          random: true,
          anim: { enable: true, speed: 0.7, opacity_min: 0.08, sync: false }
        },
        size: {
          value: 2.2,
          random: true,
          anim: { enable: true, speed: 1.5, size_min: 0.4, sync: false }
        },
        line_linked: {
          enable:   true,
          distance: 148,
          color:    "#00b8ff",
          opacity:  0.25,
          width:    1.1
        },
        move: {
          enable:    true,
          speed:     1.1,
          direction: "none",
          random:    true,
          straight:  false,
          out_mode:  "out",
          bounce:    false,
          attract:   { enable: true, rotateX: 600, rotateY: 1200 }
        }
      },
      interactivity: {
        detect_on: "window",
        events: {
          onhover: { enable: true, mode: "grab" },
          onclick: { enable: true, mode: "push" },
          resize:  true
        },
        modes: {
          grab: { distance: 175, line_linked: { opacity: 0.55 } },
          push: { particles_nb: 4 },
          repulse: { distance: 80, duration: 0.4 }
        }
      },
      retina_detect: true
    });
  })();

  /* ════════════════════════════════════════════
     17. FIELD FOCUS EFFECTS (v5.0 nâng cấp)
  ════════════════════════════════════════════ */
  [usernameInput, passwordInput].forEach(inp => {
    if (!inp) return;

    inp.addEventListener("focus", function () {
      const wrap = this.closest(".field, .field-group");
      if (wrap) {
        wrap.classList.add("field--focused");
        const label = wrap.querySelector("label");
        if (label) label.style.color = "var(--accent, #00e5ff)";
      }
    });

    inp.addEventListener("blur", function () {
      const wrap = this.closest(".field, .field-group");
      if (wrap) {
        wrap.classList.remove("field--focused");
        if (!wrap.classList.contains("has-error")) {
          const label = wrap.querySelector("label");
          if (label) label.style.color = "";
        }
      }
    });
  });

  /* ════════════════════════════════════════════
     18. AVATAR HOVER EFFECT (v5.0 MỚI)
  ════════════════════════════════════════════ */
  (function initAvatarEffect() {
    const avatarWrap = document.querySelector(".avatar-wrap");
    if (!avatarWrap) return;

    avatarWrap.addEventListener("mouseenter", function () {
      this.style.transform = "scale(1.05) translateY(-2px)";
      this.style.transition = "transform 0.3s cubic-bezier(.34,1.56,.64,1)";
    });

    avatarWrap.addEventListener("mouseleave", function () {
      this.style.transform = "";
    });

    /* Click avatar — small ripple effect */
    avatarWrap.addEventListener("click", function (e) {
      const ripple = document.createElement("div");
      const size   = Math.max(this.offsetWidth, this.offsetHeight) * 2;
      ripple.style.cssText = `
        position:absolute;width:${size}px;height:${size}px;
        border-radius:50%;background:rgba(0,229,255,0.15);
        transform:translate(-50%,-50%) scale(0);
        left:50%;top:50%;pointer-events:none;
        animation:avatarRipple 0.6s ease forwards;`;
      this.style.position = "relative";
      this.style.overflow = "hidden";
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 650);
    });

    if (!document.getElementById("__avatar_ripple_css__")) {
      const s = document.createElement("style");
      s.id = "__avatar_ripple_css__";
      s.textContent = `@keyframes avatarRipple {
        to { transform: translate(-50%,-50%) scale(1); opacity: 0; }
      }`;
      document.head.appendChild(s);
    }
  })();

  /* ════════════════════════════════════════════
     19. FORGOT PASSWORD — handle click
  ════════════════════════════════════════════ */
  const forgotLink = document.querySelector(".link.forgot, .forgot");
  if (forgotLink) {
    forgotLink.addEventListener("click", function (e) {
      e.preventDefault();
      showError("Liên hệ quản trị viên hệ thống để đặt lại mật khẩu.");
    });
  }

  /* ════════════════════════════════════════════
     20. KEYBOARD SHORTCUTS (v5.0 MỚI)
  ════════════════════════════════════════════ */
  document.addEventListener("keydown", function (e) {
    /* Alt+L: Focus username */
    if (e.altKey && e.key === "l") {
      e.preventDefault();
      if (usernameInput) usernameInput.focus();
    }
    /* Escape: Clear errors */
    if (e.key === "Escape") {
      showError("");
      clearFieldErrors();
    }
  });

  /* ════════════════════════════════════════════
     21. BOOT STATE — đọc từ index.html sessionStorage
  ════════════════════════════════════════════ */
  (function readBootState() {
    try {
      const raw   = sessionStorage.getItem(BOOT_STATE_KEY);
      if (!raw) return;
      const state = JSON.parse(raw);
      /* Nếu boot state quá cũ (>30s) thì bỏ qua */
      if (Date.now() - (state.ts || 0) > 30_000) return;

      /* Log boot state vào console (developer info) */
      const modeLabel = state.esp32
        ? "LIVE (Virtual Cluster Connected)"
        : state.server
          ? "SERVER ONLINE — Cluster Starting"
          : "AUTO MODE (Server Offline)";
      console.info(`[TrafficAI v5.0] Boot mode: ${modeLabel}`);
    } catch (_) { /* ignore */ }
  })();

  /* ════════════════════════════════════════════
     22. IF LOCKOUT ACTIVE ON PAGE LOAD (giữ từ v4.0)
  ════════════════════════════════════════════ */
  if (isLockedOut()) {
    startLockoutCountdown();
  }

  /* ════════════════════════════════════════════
     23. INPUT AUTO-COMPLETE BLOCK (v5.0)
     Ngăn browser autofill thay đổi style
  ════════════════════════════════════════════ */
  [usernameInput, passwordInput].forEach(inp => {
    if (!inp) return;
    /* Force remove autofill background after a delay */
    setTimeout(() => {
      inp.style.transition = "background-color 99999s ease, color 99999s ease";
    }, 100);
  });


  /* ╔══════════════════════════════════════════════════════════╗
     ║       v6.0 — CLUSTER LIVE TELEMETRY ENGINE                 ║
     ║  Polling real data từ virtual_esp32_cluster.py           ║
     ╚══════════════════════════════════════════════════════════╝ */

  const POLL_INTERVAL_MS = 2500;

  const _live = {
    serverOnline: false, mqttOnline: false, esp32Connected: false,
    devices: {}, context: {}, violations: 0,
    framesTotal: 0, fps: 0, pollCount: 0,
  };

  /* ── Inject v6.0 CSS ── */
  (function injectV6CSS() {
    if (document.getElementById("__v6_css__")) return;
    const s = document.createElement("style");
    s.id = "__v6_css__";
    s.textContent = `
      .v6-pipeline{display:flex;align-items:center;background:rgba(2,9,23,.6);border:1px solid rgba(0,229,255,.07);border-radius:8px;padding:7px 9px;backdrop-filter:blur(10px);margin-top:2px;width:100%;}
      .v6-pn{display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;font-family:'JetBrains Mono',monospace;font-size:6.5px;letter-spacing:.7px;text-transform:uppercase;color:#1a2a3f;transition:color .4s;}
      .v6-pn.pn-active{color:#00e87a;}.v6-pn.pn-warn{color:#ffb020;}.v6-pn.pn-offline{color:#1a2a3f;}
      .v6-pi{font-size:12px;filter:drop-shadow(0 0 3px currentColor);transition:filter .4s;}
      .v6-plat{font-size:6px;color:#00e5ff;opacity:0;transition:opacity .4s;}.v6-pn.pn-active .v6-plat{opacity:.7;}
      .v6-pa{width:12px;flex-shrink:0;text-align:center;color:#0e1a2a;font-size:9px;transition:color .4s;}
      .v6-pa.pa-active{color:#00e87a;animation:v6pf .9s ease-in-out infinite;}
      @keyframes v6pf{0%,100%{opacity:.3;transform:translateX(-2px)}50%{opacity:1;transform:translateX(2px)}}
      .v6-dev-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;width:100%;margin-top:2px;}
      .v6-dc{background:rgba(2,9,23,.55);border:1px solid rgba(74,96,128,.10);border-radius:7px;padding:7px 9px;position:relative;overflow:hidden;font-family:'JetBrains Mono',monospace;transition:all .4s;backdrop-filter:blur(8px);}
      .v6-dc::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:transparent;transition:background .4s;}
      .v6-dc.dc-on{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.035);}
      .v6-dc.dc-on::before{background:linear-gradient(90deg,transparent,rgba(0,232,122,.4),transparent);}
      .v6-dc.dc-chk{border-color:rgba(255,176,32,.18);}
      .v6-dh{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;}
      .v6-dn{font-size:7.5px;letter-spacing:1.2px;text-transform:uppercase;color:#2a3a55;transition:color .4s;}
      .v6-dc.dc-on .v6-dn{color:#00e87a;}
      .v6-ddot{width:5px;height:5px;border-radius:50%;background:#0e1a2a;transition:background .4s,box-shadow .4s;}
      .v6-dc.dc-on .v6-ddot{background:#00e87a;box-shadow:0 0 6px #00e87a;animation:v6db 1.4s ease-in-out infinite;}
      .v6-dc.dc-chk .v6-ddot{background:#ffb020;animation:v6db .7s ease-in-out infinite;}
      @keyframes v6db{0%,100%{opacity:1}50%{opacity:.2}}
      .v6-dr{display:flex;justify-content:space-between;font-size:7px;letter-spacing:.3px;line-height:1.6;}
      .v6-dl{color:#1a2a3f;}.v6-dv{color:#4a5a6a;font-weight:700;transition:color .4s;}
      .v6-dc.dc-on .v6-dv{color:#cdd9f0;}
      .v6-sig{height:2px;background:rgba(255,255,255,.05);border-radius:99px;overflow:hidden;margin-top:4px;}
      .v6-sf{height:100%;border-radius:99px;background:linear-gradient(90deg,#0077ff,#00e5ff);transition:width .7s cubic-bezier(.4,0,.2,1);}
      .v6-counters{display:flex;gap:5px;width:100%;margin-top:2px;}
      .v6-cnt{flex:1;background:rgba(2,9,23,.55);border:1px solid rgba(0,229,255,.07);border-radius:6px;padding:5px 8px;text-align:center;font-family:'JetBrains Mono',monospace;backdrop-filter:blur(8px);transition:border-color .4s;}
      .v6-cnt.hot{border-color:rgba(0,232,122,.22);}
      .v6-cv{font-size:15px;font-weight:700;color:#00e5ff;letter-spacing:-1px;line-height:1.1;}
      .v6-cnt.hot .v6-cv{color:#00e87a;}
      .v6-cl{font-size:6.5px;letter-spacing:1px;text-transform:uppercase;color:#2a3a55;margin-top:1px;}
      .v6-mqtt{display:flex;align-items:center;gap:6px;padding:5px 9px;border-radius:6px;border:1px solid rgba(74,96,128,.12);background:rgba(2,9,23,.5);font-family:'JetBrains Mono',monospace;font-size:7.5px;letter-spacing:.9px;text-transform:uppercase;color:#2a3a55;transition:all .4s;width:100%;margin-top:2px;backdrop-filter:blur(8px);}
      .v6-mqtt.m-live{border-color:rgba(0,232,122,.25);color:#00e87a;background:rgba(0,232,122,.04);}
      .v6-mqtt.m-warn{border-color:rgba(255,176,32,.22);color:#ffb020;background:rgba(255,176,32,.04);}
      .v6-mdot{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0;}
      .v6-mqtt.m-live .v6-mdot{animation:v6db 1s ease-in-out infinite;}
      .v6-mtxt{flex:1;}.v6-mfps{margin-left:auto;opacity:.6;font-size:6.5px;}
      .v6-ctx-row{display:flex;flex-wrap:wrap;gap:3px;width:100%;margin-top:2px;}
      .v6-gh{font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:.6px;text-transform:uppercase;padding:2px 6px;border-radius:3px;border:1px solid rgba(74,96,128,.14);background:rgba(2,9,23,.5);color:#2a3a55;transition:all .4s;}
      .v6-gh.gh-ok{border-color:rgba(0,232,122,.24);color:#00e87a;background:rgba(0,232,122,.04);}
      .v6-gh.gh-err{border-color:rgba(255,58,92,.26);color:#ff3a5c;background:rgba(255,58,92,.04);animation:v6ge 1.2s ease-in-out infinite;}
      @keyframes v6ge{0%,100%{opacity:1}50%{opacity:.4}}
      .v6-lbl{font-family:'JetBrains Mono',monospace;font-size:7px;letter-spacing:1.8px;text-transform:uppercase;color:#1a2a3f;display:flex;align-items:center;gap:6px;width:100%;margin-top:6px;}
      .v6-lbl::after{content:'';flex:1;height:1px;background:rgba(0,229,255,.05);}
      .v6-esp-warn{display:none;align-items:center;gap:7px;padding:6px 10px;border-radius:6px;margin-bottom:10px;border:1px solid rgba(255,176,32,.22);background:rgba(255,176,32,.05);font-family:'Inter',sans-serif;font-size:10.5px;color:#ffb020;}
      .v6-esp-warn.show{display:flex;}
      .v6-esp-warn svg{width:12px;height:12px;flex-shrink:0;}
      .v6-live-badge{position:absolute;bottom:-2px;left:50%;transform:translateX(-50%);font-family:'JetBrains Mono',monospace;font-size:6.5px;letter-spacing:1px;text-transform:uppercase;padding:2px 5px;border-radius:3px;background:#00e87a;color:#000;font-weight:700;opacity:0;transition:opacity .5s;pointer-events:none;white-space:nowrap;}
      .v6-live-badge.show{opacity:1;animation:v6lb 2s ease-in-out infinite;}
      @keyframes v6lb{0%,100%{opacity:1}50%{opacity:.35}}
    `;
    document.head.appendChild(s);
  })();

  /* ── Build v6.0 UI blocks ── */
  (function buildV6UI() {
    const branding = document.querySelector(".panel__inner, .branding");
    if (!branding) return;

    const pipeline = document.createElement("div");
    pipeline.innerHTML = `
      <div class="v6-lbl">Data Pipeline</div>
      <div class="v6-pipeline" id="v6Pipe">
        <div class="v6-pn pn-offline" id="pN_esp32"><span class="v6-pi">📷</span><span>ESP32</span><span class="v6-plat" id="pL_e">—</span></div>
        <div class="v6-pa" id="pA1">›</div>
        <div class="v6-pn pn-offline" id="pN_mqtt"><span class="v6-pi">📡</span><span>MQTT</span><span class="v6-plat" id="pL_m">—</span></div>
        <div class="v6-pa" id="pA2">›</div>
        <div class="v6-pn pn-offline" id="pN_server"><span class="v6-pi">⚙️</span><span>Server</span><span class="v6-plat" id="pL_s">—</span></div>
        <div class="v6-pa" id="pA3">›</div>
        <div class="v6-pn pn-offline" id="pN_ai"><span class="v6-pi">🤖</span><span>AI</span><span class="v6-plat" id="pL_a">—</span></div>
        <div class="v6-pa" id="pA4">›</div>
        <div class="v6-pn pn-offline" id="pN_dash"><span class="v6-pi">🖥️</span><span>Dash</span><span class="v6-plat" id="pL_d">—</span></div>
      </div>`;

    const devGrid = document.createElement("div");
    devGrid.innerHTML = `
      <div class="v6-lbl">Device Telemetry</div>
      <div class="v6-dev-grid" id="v6DevGrid">
        ${["cam_1","cam_2","cam_3","main"].map(k => {
          const lbl = k==="main"?"CTRL":`CAM-${k.split("_")[1]}`;
          const pfx = k==="main"?"main":`cam${k.split("_")[1]}`;
          return `<div class="v6-dc dc-off" id="v6D_${k}">
            <div class="v6-dh"><span class="v6-dn">${lbl}</span><span class="v6-ddot"></span></div>
            <div class="v6-dr"><span class="v6-dl">RSSI</span><span class="v6-dv" id="vR_${pfx}">—</span></div>
            <div class="v6-dr"><span class="v6-dl">TEMP</span><span class="v6-dv" id="vT_${pfx}">—</span></div>
            <div class="v6-dr"><span class="v6-dl">UP</span><span class="v6-dv" id="vU_${pfx}">—</span></div>
            <div class="v6-sig"><div class="v6-sf" id="vS_${pfx}" style="width:0%"></div></div>
          </div>`;
        }).join("")}
      </div>`;

    const liveRow = document.createElement("div");
    liveRow.innerHTML = `
      <div class="v6-lbl">Live Stream</div>
      <div class="v6-counters">
        <div class="v6-cnt" id="v6CntFPS"><div class="v6-cv" id="v6FPS">0</div><div class="v6-cl">FPS</div></div>
        <div class="v6-cnt" id="v6CntViol"><div class="v6-cv" id="v6Viol">0</div><div class="v6-cl">Vi phạm</div></div>
        <div class="v6-cnt" id="v6CntDev"><div class="v6-cv" id="v6DevOn">0/5</div><div class="v6-cl">Devices</div></div>
      </div>
      <div class="v6-mqtt" id="v6Mqtt">
        <span class="v6-mdot"></span>
        <span class="v6-mtxt" id="v6MqttTxt">MQTT — Chờ kết nối...</span>
        <span class="v6-mfps" id="v6MqttFPS"></span>
      </div>`;

    const ctxRow = document.createElement("div");
    ctxRow.innerHTML = `
      <div class="v6-lbl">Context Limits GH1–GH7</div>
      <div class="v6-ctx-row" id="v6CtxRow">
        <span class="v6-gh" id="v6GH1">GH1:—</span>
        <span class="v6-gh" id="v6GH2">GH2:—</span>
        <span class="v6-gh" id="v6GH3">GH3:—</span>
        <span class="v6-gh" id="v6GH4">GH4:—</span>
        <span class="v6-gh" id="v6GH5">GH5:—</span>
        <span class="v6-gh" id="v6GH6">GH6:—</span>
        <span class="v6-gh" id="v6GH7">GH7:—</span>
      </div>`;

    const ticker = branding.querySelector(".metrics-ticker");
    [pipeline, devGrid, liveRow, ctxRow].forEach(el => {
      ticker ? branding.insertBefore(el, ticker) : branding.appendChild(el);
    });

    /* LIVE badge on avatar */
    const aw = document.querySelector(".avatar-wrap");
    if (aw) {
      const b = document.createElement("div");
      b.id = "v6LiveBadge"; b.className = "v6-live-badge"; b.textContent = "CLUSTER LIVE";
      aw.appendChild(b);
    }

    /* Warning banner trong card */
    const sBar = document.getElementById("serverStatusBar");
    if (sBar) {
      const w = document.createElement("div");
      w.id = "v6EspWarn"; w.className = "v6-esp-warn";
      w.innerHTML = `<svg viewBox="0 0 16 16" fill="none"><path d="M8 2L14 13H2L8 2Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 7v3M8 11.5v.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <span id="v6WarnTxt">Virtual Cluster chưa kết nối — đang chờ data</span>`;
      sBar.after(w);
    }
  })();

  /* ── Helpers ── */
  const $v = id => document.getElementById(id);
  const fmtUp = s => { if (!s||s<0) return"—"; if(s<60) return`${Math.floor(s)}s`; if(s<3600) return`${Math.floor(s/60)}m`; return`${Math.floor(s/3600)}h${Math.floor((s%3600)/60)}m`; };
  const rssiPct = r => Math.max(0,Math.min(100,Math.round((Math.abs(r||-100)-40)/60*-100+100)));

  function setPipe(nId, aId, state, latMs) {
    const n=$v(nId); const a=aId?$v(aId):null;
    if(!n) return;
    n.className=`v6-pn pn-${state}`;
    if(a) a.className=`v6-pa ${state==="active"?"pa-active":""}`;
    const l=n.querySelector(".v6-plat");
    if(l&&latMs!=null) l.textContent=latMs+"ms";
  }

  function updateDevCard(k, data) {
    const card=$v(`v6D_${k}`); if(!card) return;
    const online=data&&data.status==="ONLINE";
    const chk=data&&data.status==="CHECKING";
    card.className=`v6-dc ${online?"dc-on":chk?"dc-chk":"dc-off"}`;
    const pfx=k==="main"?"main":`cam${k.split("_")[1]}`;
    if(online&&data) {
      const rssi=data.signal||data.rssi||0;
      const rEl=$v(`vR_${pfx}`),tEl=$v(`vT_${pfx}`),uEl=$v(`vU_${pfx}`),sEl=$v(`vS_${pfx}`);
      if(rEl) rEl.textContent=`${rssi}dBm`;
      if(tEl) tEl.textContent=`${data.temp||0}°C`;
      if(uEl) uEl.textContent=fmtUp(data.uptime||0);
      if(sEl) sEl.style.width=`${rssiPct(rssi)}%`;
    }
  }

  function updateCtx(ctx, errs) {
    const e=errs||[]; const has=ctx&&Object.keys(ctx).length>0;
    const defs=[
      {id:"v6GH1",k:"speed_kmh",      f:v=>v!=null?`GH1:${v.toFixed(1)}km/h`:"GH1:—"},
      {id:"v6GH2",k:"vehicles_frame", f:v=>v!=null?`GH2:${v}xe`:"GH2:—"},
      {id:"v6GH3",k:"weather",        f:v=>v?`GH3:${v}`:"GH3:—"},
      {id:"v6GH4",k:"distance",       f:v=>v!=null?`GH4:${v}m`:"GH4:—"},
      {id:"v6GH5",k:"roi",            f:v=>v?`GH5:${v.replace("_"," ")}`:"GH5:—"},
      {id:"v6GH6",k:"capture_interval",f:v=>v!=null?`GH6:${v}s`:"GH6:—"},
      {id:"v6GH7",k:"target_objects", f:v=>Array.isArray(v)?`GH7:${v.length}obj`:"GH7:—"},
    ];
    defs.forEach(d=>{
      const el=$v(d.id); if(!el) return;
      el.textContent=d.f(ctx?ctx[d.k]:undefined);
      const hasErr=e.some(x=>typeof x==="string"&&x.toLowerCase().includes(d.k.replace("_","")));
      el.className=`v6-gh ${has?(hasErr?"gh-err":"gh-ok"):""}`;
    });
  }

  /* ── Sync v5.0 elements ── */
  function syncV5() {
    const sp=(c,t)=>{const p=$v("serverPill"),pt=$v("serverPillTxt");if(p)p.className=`server-pill server-pill--${c}`;if(pt)pt.textContent=t;};
    const sb=(c,t)=>{const b=$v("serverStatusBar"),bt=$v("serverBarTxt");if(b)b.className=`server-status-bar server-status-bar--${c}`;if(bt)bt.textContent=t;};
    const mb=(c,t)=>{const m=$v("modeBadge"),mt=$v("modeBadgeTxt");if(m)m.className=`mode-badge mode-badge--${c}`;if(mt)mt.textContent=t;};
    const sc=(ci,vi,s,l)=>{const c=$v(ci),v=$v(vi);if(c)c.className=`device-chip device-chip--${s}`;if(v)v.textContent=l;};
    const qh=$v("quickHint"); const id=$v("iotDot"); const il=$v("iotLabel");

    if(!_live.serverOnline) {
      sp("offline","⚡ OFFLINE"); sb("offline","⚡ Máy chủ offline — Tự vận hành"); mb("auto","⚡ AUTO MODE");
      sc("chipEsp32","chipEsp32Val","offline","OFFLINE"); sc("chipMqtt","chipMqttVal","offline","OFFLINE"); sc("chipCam","chipCamVal","offline","OFFLINE");
      if(id)id.className="dot dot--yellow"; if(il)il.textContent="IoT Standby"; if(qh)qh.style.display="flex";
      return;
    }
    if(qh)qh.style.display="none";
    sc("chipMqtt","chipMqttVal",_live.mqttOnline?"online":"offline",_live.mqttOnline?"ONLINE":"STANDBY");
    if(_live.esp32Connected) {
      sp("online","🟢 LIVE — VIRTUAL CLUSTER ONLINE"); sb("online","✔ Virtual Data Cluster kết nối — Hệ thống thực tế"); mb("live","🔴 HỆ THỐNG THỰC TẾ");
      sc("chipEsp32","chipEsp32Val","online","ONLINE"); sc("chipCam","chipCamVal","online","LIVE");
      if(id)id.className="dot dot--green blink"; if(il)il.textContent="Cluster Live";
    } else {
      sp("ready","⚡ SERVER ONLINE"); sb("online","⚡ Sẵn sàng — Cluster chưa kết nối"); mb("ready","⚡ SERVER ONLINE — Chờ Cluster");
      sc("chipEsp32","chipEsp32Val","offline","OFFLINE"); sc("chipCam","chipCamVal","offline","STANDBY");
      if(id)id.className="dot dot--yellow"; if(il)il.textContent="IoT Waiting";
    }
  }

  /* ── Main poll ── */
  async function pollTelemetry() {
    const tok=localStorage.getItem("TRAFFIC_AI_TOKEN")||"TRAFFIC_AI_TOKEN";
    const hdr={"Authorization":`Bearer ${tok}`};
    const t0=Date.now();
    try {
      const hRes=await fetch("/api/health",{headers:hdr,signal:AbortSignal.timeout(3000)});
      const hData=await hRes.json();
      const lat=Date.now()-t0;
      if(!hData||!hData.ok) throw new Error("health_fail");

      _live.serverOnline=true; _live.mqttOnline=!!(hData.mqtt);

      setPipe("pN_server","pA3","active",lat);
      setPipe("pN_ai",    "pA4",_live.mqttOnline?"active":"warn",null);
      setPipe("pN_dash",  null, "active",null);
      setPipe("pN_mqtt",  "pA2",_live.mqttOnline?"active":"warn",null);

      const bRes=await fetch("/api/bootstrap",{headers:hdr,signal:AbortSignal.timeout(3000)});
      const bData=await bRes.json();

      if(bData&&bData.ok) {
        const devs=bData.devices||{};
        _live.devices=devs;
        ["cam_1","cam_2","cam_3","main"].forEach(k=>updateDevCard(k,devs[`esp32_${k}`]));

        const onCnt=Object.values(devs).filter(d=>d&&d.status==="ONLINE").length;
        const doEl=$v("v6DevOn"); if(doEl)doEl.textContent=`${onCnt}/${Object.keys(devs).length}`;

        _live.esp32Connected=["esp32_cam_1","esp32_cam_2","esp32_cam_3","esp32_main"].some(
          id=>devs[id]&&devs[id].status==="ONLINE"
        );
        setPipe("pN_esp32","pA1",_live.esp32Connected?"active":"warn",null);

        if(bData.stats) {
          const prevV=_live.violations;
          _live.violations=bData.stats.violations_today||_live.violations;
          const vEl=$v("v6Viol"); if(vEl)vEl.textContent=_live.violations;
          const vCnt=$v("v6CntViol"); if(vCnt)vCnt.classList.toggle("hot",_live.violations>prevV);

          if(bData.stats.frames_processed!=null) {
            const diff=bData.stats.frames_processed-_live.framesTotal;
            if(diff>0) _live.fps=Math.round(diff/(POLL_INTERVAL_MS/1000));
            _live.framesTotal=bData.stats.frames_processed;
          }
        }

        const ctx=bData.context_state||{};
        _live.context=ctx;
        updateCtx(ctx,bData.context_errors);

        const mqEl=$v("v6Mqtt"),mqTx=$v("v6MqttTxt"),mqFP=$v("v6MqttFPS");
        if(mqEl) {
          if(_live.mqttOnline&&_live.esp32Connected){mqEl.className="v6-mqtt m-live";if(mqTx)mqTx.textContent="MQTT LIVE — Virtual Data Cluster";}
          else if(_live.mqttOnline){mqEl.className="v6-mqtt m-warn";if(mqTx)mqTx.textContent="MQTT ONLINE — Chờ Virtual Cluster";}
          else{mqEl.className="v6-mqtt";if(mqTx)mqTx.textContent="MQTT OFFLINE";}
          if(mqFP)mqFP.textContent=`${_live.fps} FPS`;
        }

        const fEl=$v("v6FPS"); if(fEl)fEl.textContent=_live.fps;
        const fCnt=$v("v6CntFPS"); if(fCnt)fCnt.classList.toggle("hot",_live.fps>5);

        const warn=$v("v6EspWarn");
        if(warn) {
          if(_live.serverOnline&&!_live.esp32Connected){warn.classList.add("show");const wt=$v("v6WarnTxt");if(wt)wt.textContent=`Server online — Virtual Cluster đang khởi động`;}
          else warn.classList.remove("show");
        }
        const lb=$v("v6LiveBadge"); if(lb)lb.classList.toggle("show",_live.esp32Connected);
      }
      syncV5();
    } catch(err) {
      _live.serverOnline=false; _live.mqttOnline=false; _live.esp32Connected=false;
      ["pN_esp32","pN_mqtt","pN_server","pN_ai","pN_dash"].forEach(n=>setPipe(n,null,"offline",null));
      ["pA1","pA2","pA3","pA4"].forEach(a=>{const el=$v(a);if(el)el.className="v6-pa";});
      ["cam_1","cam_2","cam_3","main"].forEach(k=>updateDevCard(k,null));
      const mqEl=$v("v6Mqtt"),mqTx=$v("v6MqttTxt");
      if(mqEl)mqEl.className="v6-mqtt"; if(mqTx)mqTx.textContent="Server offline — Hệ thống tự vận hành";
      const lb=$v("v6LiveBadge"); if(lb)lb.classList.remove("show");
      const warn=$v("v6EspWarn"); if(warn)warn.classList.remove("show");
      syncV5();
    }
  }

  /* ── Start polling ── */
  setTimeout(()=>{ pollTelemetry(); setInterval(pollTelemetry,POLL_INTERVAL_MS); },800);

  /* ── Boot state save on unload ── */
  window.addEventListener("beforeunload",()=>{
    try {
      sessionStorage.setItem("TRAFFIC_BOOT_STATE",JSON.stringify({
        mode:_live.esp32Connected?"real":_live.serverOnline?"simulating":"auto",
        server:_live.serverOnline,esp32:_live.esp32Connected,mqtt:_live.mqttOnline,ts:Date.now()
      }));
      sessionStorage.setItem("TRAFFIC_LIVE_STATE_V6",JSON.stringify({
        serverOnline:_live.serverOnline,mqttOnline:_live.mqttOnline,
        esp32Connected:_live.esp32Connected,devices:_live.devices,
        violations:_live.violations,fps:_live.fps,ts:Date.now()
      }));
    } catch(_){}
  });


})();