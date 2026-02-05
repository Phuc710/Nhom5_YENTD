// loginlogic.js
(function () {
  "use strict";

  const TOKEN_KEY = "TRAFFIC_AI_TOKEN";
  const form = document.getElementById("loginForm");
  const msg = document.getElementById("msg");

  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (msg) {
      msg.textContent = "";
      msg.className = "msg";
    }

    const username = document.getElementById("username")?.value?.trim() || "";
    const password = document.getElementById("password")?.value || "";

    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await r.json().catch(() => ({}));

      if (!r.ok || !data.ok || !data.token) {
        if (msg) {
          msg.textContent = data.error || "Đăng nhập thất bại";
          msg.className = "msg err";
        }
        return;
      }

      // ✅ FIX: lưu đúng key (và dọn key cũ nếu còn)
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.removeItem("token");

      if (msg) {
        msg.textContent = "Đăng nhập thành công...";
        msg.className = "msg ok";
      }

      setTimeout(() => {
        window.location.href = "/main.html";
      }, 150);
    } catch (err) {
      if (msg) {
        msg.textContent = "Lỗi kết nối server";
        msg.className = "msg err";
      }
    }
  });
})();
