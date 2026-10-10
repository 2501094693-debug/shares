/* 同花顺扫码登录：右上角状态点 + 弹窗二维码，轮询到登录成功后自动刷新行情。 */
(function () {
  "use strict";
  var BTN_ID = "thsAuthBtn";
  var MODAL_ID = "thsAuthModal";
  var timer = 0;
  var open = false;

  function el(id) { return document.getElementById(id); }
  function needQr(msg) { return String(msg || "").indexOf("THS_NEED_QRCODE") >= 0; }
  function api(path, method) {
    return fetch(path, { method: method || "GET", cache: "no-store" }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: "响应解析失败" }; }).then(function (j) {
        if (!r.ok && !j.data) throw new Error((j && j.error) || ("请求失败 " + r.status));
        return j;
      });
    });
  }

  function showModalSync() {
    open = true;
    var m = el(MODAL_ID);
    if (m) { m.classList.remove("hidden"); m.style.display = "flex"; }
    var hint = el("thsQrHint");
    if (hint) hint.textContent = "正在生成二维码…";
  }

  var ThsAuth = {
    notifyMaybeAuthError: function (msg) {
      if (needQr(msg)) this.openModal();
      else this.refreshBadge();
    },
    refreshBadge: function () {
      return api("/api/stocks/ths-auth/status").then(function (j) {
        var d = (j && j.data) || {};
        var b = el(BTN_ID);
        if (!b) return;
        var dot = b.querySelector(".ths-dot");
        var st = d.authenticated ? "ok" : (d.pending ? "pending" : "idle");
        b.dataset.state = st;
        if (dot) dot.dataset.state = st;
        b.title = d.authenticated ? "同花顺已登录，会话已持久化，无需重复扫码"
          : (d.pending ? "同花顺待扫码，点击查看二维码" : "同花顺未登录，点击扫码（一次登录长期有效）");
      }).catch(function (e) { console.warn("[ths-auth] status 失败", e); });
    },
    openModal: function () {
      showModalSync();
      api("/api/stocks/ths-auth/start", "POST").catch(function (e) {
        console.warn("[ths-auth] start 失败", e);
        var hint = el("thsQrHint");
        if (hint) hint.textContent = "启动登录失败：" + (e.message || e) + "（后端没重启会 404/405，请先重启后端）";
      });
      this.poll();
    },
    closeModal: function () {
      open = false;
      if (timer) clearInterval(timer);
      timer = 0;
      var m = el(MODAL_ID);
      if (m) { m.classList.add("hidden"); m.style.display = "none"; }
    },
    poll: function () {
      var self = this;
      if (timer) clearInterval(timer);
      const tick = async () => {
        if (!open) return;
        try {
          const j = await api("/api/stocks/ths-auth/status");
          const d = (j && j.data) || {};
          const img = el("thsQrImg"), scan = el("thsQrScan"), hint = el("thsQrHint");
          if (d.authenticated) {
            if (hint) hint.textContent = "登录成功，会话已保存，后续自动复用无需再扫。正在刷新行情…";
            if (img) img.style.display = "none";
            self.refreshBadge();
            self.closeModal();
            window.location.reload();
            return;
          }
          if (d.image_url && img) {
            img.style.display = "";
            if (img.getAttribute("src") !== d.image_url) img.src = d.image_url;
          } else if (img && !d.pending) {
            img.style.display = "none";
          }
          if (scan) {
            if (d.scan_url) { scan.href = d.scan_url; scan.hidden = false; scan.textContent = "打不开图？点此打开扫码地址"; }
            else scan.hidden = true;
          }
          if (hint) hint.textContent = d.error || (d.pending ? "请用同花顺手机客户端扫码确认（二维码约3分钟有效）" : "正在生成二维码…");
        } catch (e) {
          var hint = el("thsQrHint");
          if (hint) hint.textContent = "状态查询失败：" + (e.message || e) + "（后端没重启会 404，请先重启后端）";
        }
        self.refreshBadge();
      };
      tick();
      timer = setInterval(tick, 2000);
    }
  };
  window.ThsAuth = ThsAuth;
  window.openThsAuth = function () { ThsAuth.openModal(); };

  function bind() {
    var b = el(BTN_ID);
    if (b && !b.dataset.thsBound) {
      b.dataset.thsBound = "1";
      b.addEventListener("click", function (e) { e.preventDefault(); ThsAuth.openModal(); });
    }
    var c = el("thsAuthClose");
    if (c && !c.dataset.thsBound) {
      c.dataset.thsBound = "1";
      c.addEventListener("click", function () { ThsAuth.closeModal(); });
    }
    var m = el(MODAL_ID);
    if (m && !m.dataset.thsBound) {
      m.dataset.thsBound = "1";
      m.addEventListener("click", function (e) { if (e.target === m) ThsAuth.closeModal(); });
    }
    var cancel = el("thsAuthCancel");
    if (cancel && !cancel.dataset.thsBound) {
      cancel.dataset.thsBound = "1";
      cancel.addEventListener("click", function () {
        api("/api/stocks/ths-auth/cancel", "POST").catch(function () {}).finally(function () { ThsAuth.closeModal(); });
      });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { bind(); ThsAuth.refreshBadge(); });
  else { bind(); ThsAuth.refreshBadge(); }
  setTimeout(function () { bind(); ThsAuth.refreshBadge(); }, 1500);

  var _fetch = window.fetch.bind(window);
  window.fetch = function () {
    var args = arguments;
    return _fetch.apply(null, args).then(function (r) {
      try {
        var url = String(args[0] || "");
        if (/\/api\/stocks\/(line|ticks|fund-flow)/.test(url)) {
          r.clone().json().catch(function () { return null; }).then(function (j) {
            if (j && j.ok === false && needQr(j.error) && window.ThsAuth) window.ThsAuth.notifyMaybeAuthError(j.error);
          });
        }
      } catch (e) { /* ignore */ }
      return r;
    });
  };
  console.log("[ths-auth] loaded");
})();
