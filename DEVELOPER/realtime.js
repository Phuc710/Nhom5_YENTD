"use strict";

// Realtime bridge for frontend (SSE)
// Dispatches CustomEvent on window:
// - camera_status_updated
// - violation_created
// - realtime_system
(function initRealtimeBridge() {
  const TOKEN_KEY = "TRAFFIC_AI_TOKEN";
  let es = null;
  let retryTimer = null;
  let started = false;

  function getToken() {
    return String(localStorage.getItem(TOKEN_KEY) || "").trim();
  }

  function dispatch(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function normalizeAndDispatch(message) {
    const type = String(message?.type || "").toLowerCase();
    const payload = message?.payload || {};
    // New event names
    if (type === "camera_status_updated") {
      dispatch("camera_status_updated", payload);
      return;
    }
    if (type === "violation_created") {
      dispatch("violation_created", payload);
      return;
    }
    // Backward compatibility aliases
    if (type === "heartbeat" || type === "status") {
      dispatch("camera_status_updated", payload);
      return;
    }
    if (type === "violation") {
      dispatch("violation_created", payload);
      return;
    }
    dispatch("realtime_system", message);
  }

  function scheduleReconnect() {
    if (retryTimer) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      start();
    }, 5000);
  }

  function start() {
    if (es) return;
    const token = getToken();
    if (!token) return;
    const url = `/api/realtime/events?token=${encodeURIComponent(token)}`;
    try {
      es = new EventSource(url);
      es.onopen = () => dispatch("realtime_system", { type: "system_event", payload: { event: "connected" } });
      es.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data || "{}");
          normalizeAndDispatch(msg);
        } catch (_) {
          // ignore malformed packet
        }
      };
      es.onerror = () => {
        if (es) {
          es.close();
          es = null;
        }
        scheduleReconnect();
      };
    } catch (_) {
      scheduleReconnect();
    }
  }

  function stop() {
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    if (es) {
      es.close();
      es = null;
    }
  }

  window.RealtimeBridge = {
    start() {
      if (started) return;
      started = true;
      start();
    },
    stop,
    isStarted() {
      return started;
    },
  };
})();

