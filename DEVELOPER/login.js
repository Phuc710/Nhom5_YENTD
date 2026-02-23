/**
 * TrafficAI — Unified Login Controller
 * login.js  |  Premium Neural Authentication Module — COMBINED
 *
 * Merges: Original Premium Module + Neural Upgrade 2026
 *
 * Features:
 *  - Standard credential login  (/api/login)
 *  - Legacy fallback credentials (env/config override)
 *  - Remember-me via localStorage
 *  - Field-level validation with UX feedback
 *  - Abort controller / 8s timeout
 *  - Brute-force lockout (5 attempts → 30s cooldown)
 *  - Particles.js animated background
 *  - Advanced shake & success animations
 *  - Countdown timer UI for lockout state
 */

(function () {
  "use strict";

  /* ── Constants ── */
  const TOKEN_KEY       = "TRAFFIC_AI_TOKEN";
  const REMEMBER_KEY    = "TRAFFIC_AI_REMEMBER";
  const LOCKOUT_KEY     = "TRAFFIC_AI_LOCKOUT";
  const MAX_ATTEMPTS    = 5;
  const LOCKOUT_MS      = 30_000;          // 30 seconds
  const REQUEST_TIMEOUT = 8_000;           // 8 seconds

  /* ── Legacy / offline fallback credentials
       (used when the /api/login endpoint is unavailable or returns 404)
       In production, remove or replace with a real back-end.         ── */
  const LEGACY_USERS = [
    { username: "admin",    password: "admin123",  role: "superadmin" },
  ];

  /* ── DOM References ── */
  const form          = document.getElementById("loginForm");
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const loginBtn      = document.getElementById("loginBtn");
  const errorBox      = document.getElementById("errorBox");
  const togglePwBtn   = document.getElementById("togglePw");
  const rememberMe    = document.getElementById("rememberMe");

  if (!form) return; // Guard: not on login page

  /* ────────────────────────────────────────────
     1.  REMEMBER-ME — restore saved username
  ──────────────────────────────────────────── */
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

  /* ────────────────────────────────────────────
     2.  LOCKOUT GUARD
  ──────────────────────────────────────────── */
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
    const { lockedUntil } = getLockoutState();
    return Date.now() < lockedUntil;
  }

  function remainingLockout() {
    const { lockedUntil } = getLockoutState();
    return Math.max(0, Math.ceil((lockedUntil - Date.now()) / 1000));
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

  /* ── Lockout countdown timer ── */
  let lockoutTimer = null;

  function startLockoutCountdown() {
    clearInterval(lockoutTimer);
    loginBtn.disabled = true;
    loginBtn.classList.remove("loading");

    // Remove spinner / arrow, show text only
    const textEl = loginBtn.querySelector(".btn-submit__text, .text");
    const spinnerEl = loginBtn.querySelector(".btn-submit__spinner, .spinner");
    const arrowEl = loginBtn.querySelector(".btn-submit__arrow");

    if (spinnerEl) spinnerEl.style.display = "none";
    if (arrowEl) arrowEl.style.display = "none";

    lockoutTimer = setInterval(() => {
      const secs = remainingLockout();
      if (secs <= 0) {
        clearInterval(lockoutTimer);
        lockoutTimer = null;
        loginBtn.disabled = false;
        if (textEl) textEl.textContent = "Authenticate";
        if (arrowEl) arrowEl.style.display = "";
        showError("");
        return;
      }
      if (textEl) textEl.textContent = `Locked (${secs}s)`;
      showError(`Too many attempts. Try again in ${secs}s.`);
    }, 1000);

    // immediate tick
    const secs = remainingLockout();
    if (textEl) textEl.textContent = `Locked (${secs}s)`;
    showError(`Too many attempts. Try again in ${secs}s.`);
  }

  /* ────────────────────────────────────────────
     3.  UI HELPERS
  ──────────────────────────────────────────── */
  function setLoading(active, locked = false) {
    loginBtn.disabled = active;

    if (active && !locked) {
      loginBtn.classList.add("loading");
    } else {
      loginBtn.classList.remove("loading");

      if (!locked) {
        // Rebuild button inner HTML cleanly
        loginBtn.innerHTML = `
          <span class="btn-submit__text text">Authenticate</span>
          <span class="btn-submit__spinner spinner"></span>
          <svg class="btn-submit__arrow" viewBox="0 0 20 20" fill="none">
            <path d="M4 10h12M12 6l4 4-4 4" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
          </svg>`;
      }
    }
  }

  function showError(msg) {
    if (!errorBox) return;
    errorBox.textContent = msg || "";
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

  /* ────────────────────────────────────────────
     4.  SAVE / CLEAR SESSION
  ──────────────────────────────────────────── */
  function saveSession(token, username) {
    localStorage.setItem(TOKEN_KEY, token);

    if (rememberMe && rememberMe.checked) {
      localStorage.setItem(REMEMBER_KEY, JSON.stringify({ username }));
    } else {
      localStorage.removeItem(REMEMBER_KEY);
    }
  }

  /* ────────────────────────────────────────────
     5.  LEGACY FALLBACK AUTH
        Used when API endpoint is unavailable.
  ──────────────────────────────────────────── */
  function legacyAuth(username, password) {
    const user = LEGACY_USERS.find(
      u => u.username === username && u.password === password
    );
    if (!user) return null;

    // Generate a pseudo-token (base64 — NOT production-safe)
    const ts  = Date.now();
    const raw = `${user.username}:${user.role}:${ts}`;
    const b64 = btoa(raw);
    return { token: `legacy.${b64}`, role: user.role };
  }

  /* ────────────────────────────────────────────
     6.  PRIMARY AUTH — hits /api/login
  ──────────────────────────────────────────── */
  async function apiAuth(username, password) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      // 404 / network-level non-JSON: fall through to legacy
      const ct = response.headers.get("content-type") || "";
      if (!ct.includes("application/json")) {
        return { useLegacy: true };
      }

      const data = await response.json().catch(() => ({}));

      // Explicit server failure
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

      if (err.name === "AbortError") {
        return { error: "Request timed out. Check your connection." };
      }
      // Network error (no server) → fall back to legacy
      if (err.name === "TypeError") {
        return { useLegacy: true };
      }

      return { error: err.message || "An unexpected error occurred." };
    }
  }

  /* ────────────────────────────────────────────
     7.  SHAKE ANIMATION — card + DOM helper
  ──────────────────────────────────────────── */
  function shakeCard() {
    const card = document.querySelector(".card, .login-card");
    if (!card) return;
    card.style.animation = "none";
    card.offsetHeight; // force reflow
    card.style.animation = "shake .42s ease";
    setTimeout(() => { card.style.animation = ""; }, 420);
  }

  /* ────────────────────────────────────────────
     8.  FORM SUBMIT HANDLER
  ──────────────────────────────────────────── */
  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    /* Lockout check */
    if (isLockedOut()) {
      startLockoutCountdown();
      return;
    }

    const username = usernameInput.value.trim();
    const password = passwordInput.value; // Do NOT trim password

    if (!validateInputs(username, password)) return;

    showError("");
    setLoading(true);

    /* ── Attempt API auth first ── */
    let result = await apiAuth(username, password);

    /* ── Fallback to legacy if API unavailable ── */
    if (result.useLegacy) {
      const legacy = legacyAuth(username, password);
      if (legacy) {
        result = legacy;
      } else {
        result = { error: "Invalid credentials." };
      }
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
      const remaining = MAX_ATTEMPTS - attempts;
      const suffix = remaining > 0
        ? ` (${remaining} attempt${remaining !== 1 ? "s" : ""} remaining)`
        : "";

      showError(result.error + suffix);
      shakeCard();
      return;
    }

    /* ── SUCCESS ── */
    resetAttempts();
    saveSession(result.token, username);

    // Visual success feedback
    const textEl    = loginBtn.querySelector(".btn-submit__text, .text");
    const spinnerEl = loginBtn.querySelector(".btn-submit__spinner, .spinner");
    const arrowEl   = loginBtn.querySelector(".btn-submit__arrow");

    if (spinnerEl) spinnerEl.style.display = "none";
    if (arrowEl)   arrowEl.style.display   = "none";
    if (textEl)    textEl.textContent       = "✓ Access Granted";
    if (textEl)    textEl.style.opacity     = "1";

    loginBtn.style.background  = "linear-gradient(90deg, #00ff9d, #00e5ff)";
    loginBtn.style.boxShadow   = "0 0 40px rgba(0,255,157,0.5)";
    loginBtn.style.color       = "#000";

    setTimeout(() => {
      window.location.replace("main.html");
    }, 800);
  });

  /* ────────────────────────────────────────────
     9.  PASSWORD TOGGLE
  ──────────────────────────────────────────── */
  if (togglePwBtn) {
    togglePwBtn.addEventListener("click", function () {
      const isPassword = passwordInput.type === "password";
      passwordInput.type = isPassword ? "text" : "password";

      // Support both naming conventions from both versions
      const eyeOpen   = togglePwBtn.querySelector(".eye-open, .eye-open-svg");
      const eyeClosed = togglePwBtn.querySelector(".eye-closed, .eye-closed-svg");

      if (eyeOpen)   eyeOpen.style.display   = isPassword ? "none" : "";
      if (eyeClosed) eyeClosed.style.display = isPassword ? ""     : "none";

      passwordInput.focus();
    });
  }

  /* ────────────────────────────────────────────
     10. CLEAR FIELD ERROR ON TYPING
  ──────────────────────────────────────────── */
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

  /* ────────────────────────────────────────────
     11. SHAKE KEYFRAME — inject once if not in CSS
  ──────────────────────────────────────────── */
  if (!document.getElementById("__shake_kf__") && !document.getElementById("shake-style")) {
    const style = document.createElement("style");
    style.id = "__shake_kf__";
    style.textContent = `
      @keyframes shake {
        0%,100% { transform: translateX(0); }
        20%      { transform: translateX(-8px); }
        40%      { transform: translateX(8px); }
        60%      { transform: translateX(-5px); }
        80%      { transform: translateX(5px); }
      }`;
    document.head.appendChild(style);
  }

  /* ────────────────────────────────────────────
     12. PARTICLES.JS BACKGROUND ANIMATION
  ──────────────────────────────────────────── */
  (function initParticles() {
    if (typeof particlesJS === "undefined") return;

    particlesJS("particles", {
      particles: {
        number: { value: 55, density: { enable: true, value_area: 900 } },
        color: { value: "#00e5ff" },
        shape: { type: "circle" },
        opacity: { value: 0.35, random: true, anim: { enable: true, speed: 0.6, opacity_min: 0.1, sync: false } },
        size: { value: 2.2, random: true, anim: { enable: false } },
        line_linked: {
          enable: true,
          distance: 145,
          color: "#00b8ff",
          opacity: 0.28,
          width: 1.1
        },
        move: {
          enable: true,
          speed: 1.2,
          direction: "none",
          random: false,
          straight: false,
          out_mode: "out",
          bounce: false,
        }
      },
      interactivity: {
        detect_on: "canvas",
        events: {
          onhover: { enable: true, mode: "grab" },
          onclick: { enable: true, mode: "push" },
          resize: true
        },
        modes: {
          grab: { distance: 180, line_linked: { opacity: 0.55 } },
          push: { particles_nb: 4 }
        }
      },
      retina_detect: true
    });
  })();

  /* ────────────────────────────────────────────
     13. IF LOCKOUT ACTIVE ON PAGE LOAD (e.g. after refresh)
  ──────────────────────────────────────────── */
  if (isLockedOut()) {
    startLockoutCountdown();
  }

})();