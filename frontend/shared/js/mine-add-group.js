(() => {
  const POP_ID = "orbitMineAddPop";
  const TOAST_ID = "orbitMineAddToast";
  const CACHE_MS = 30_000;

  let groupsCache = null;
  let groupsAt = 0;
  let current = null;
  let busy = false;

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function api(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    if (window.OrbitHttp && method === "GET") return OrbitHttp.get(path, options);
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...options, headers, cache: "no-store" });
    const json = await res.json();
    if (!res.ok || json.ok === false) {
      throw new Error(json.error || `请求失败 (${res.status})`);
    }
    return json;
  }

  function buttonHtml({ code, name } = {}) {
    const c = String(code || "").trim();
    const n = String(name || "").trim();
    if (!c) return "";
    return `<button type="button" class="btn ghost mine-add-btn" data-add-group="${esc(c)}" data-code="${esc(c)}" data-name="${esc(n)}" title="添加至分组">分组</button>`;
  }

  function ensureToast() {
    let el = document.getElementById(TOAST_ID);
    if (el) return el;
    el = document.createElement("div");
    el.id = TOAST_ID;
    el.className = "mine-add-toast";
    el.hidden = true;
    el.setAttribute("role", "status");
    document.body.appendChild(el);
    return el;
  }

  let toastTimer = 0;
  function toast(message, kind = "ok") {
    const el = ensureToast();
    el.textContent = message;
    el.dataset.kind = kind;
    el.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      el.hidden = true;
    }, 2200);
  }

  function ensurePop() {
    let el = document.getElementById(POP_ID);
    if (el) return el;
    el = document.createElement("div");
    el.id = POP_ID;
    el.className = "mine-add-pop";
    el.hidden = true;
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "添加至分组");
    document.body.appendChild(el);
    el.addEventListener("click", onPopClick);
    return el;
  }

  async function listGroups({ force = false } = {}) {
    const now = Date.now();
    if (!force && groupsCache && now - groupsAt < CACHE_MS) return groupsCache;
    const json = await api("/api/mine/groups", { bypassCache: true });
    const raw = json.data;
    groupsCache = Array.isArray(raw?.groups)
      ? raw.groups
      : Array.isArray(raw)
        ? raw
        : [];
    groupsAt = now;
    return groupsCache;
  }

  async function createGroup(name) {
    const json = await api("/api/mine/groups", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    groupsCache = null;
    return json.data;
  }

  async function addStock(groupId, code, name) {
    const payload = { code };
    if (name) payload.name = name;
    const json = await api(`/api/mine/groups/${encodeURIComponent(groupId)}/stocks`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    groupsCache = null;
    return json.data;
  }

  function close() {
    const el = document.getElementById(POP_ID);
    if (el) el.hidden = true;
    current = null;
    busy = false;
  }

  function placeNear(anchor) {
    const el = ensurePop();
    if (!anchor || !anchor.getBoundingClientRect) {
      el.style.left = "16px";
      el.style.top = "16px";
      return;
    }
    const rect = anchor.getBoundingClientRect();
    const pad = 8;
    const width = Math.min(300, window.innerWidth - pad * 2);
    el.style.width = `${width}px`;
    let left = rect.left;
    if (left + width > window.innerWidth - pad) left = window.innerWidth - pad - width;
    if (left < pad) left = pad;
    el.style.left = `${Math.round(left)}px`;
    el.style.top = "0px";
    el.hidden = false;
    const h = el.offsetHeight || 240;
    let top = rect.bottom + 6;
    if (top + h > window.innerHeight - pad) {
      top = Math.max(pad, rect.top - h - 6);
    }
    el.style.top = `${Math.round(top)}px`;
  }

  function render({ loading = false, error = "", groups = [] } = {}) {
    const el = ensurePop();
    const stock = current || { code: "", name: "" };
    const title = stock.name ? `${stock.name} · ${stock.code}` : stock.code || "股票";
    const list = Array.isArray(groups) ? groups : [];
    const body = loading
      ? `<p class="mine-add-pop__empty muted">加载分组…</p>`
      : error
        ? `<p class="mine-add-pop__empty mine-add-pop__err">${esc(error)}</p>`
        : list.length
          ? `<ul class="mine-add-pop__list">${list
              .map(
                (g) => `<li>
              <button type="button" class="mine-add-pop__item" data-group-id="${esc(g.id)}" data-group-name="${esc(g.name || "")}">
                <span class="mine-add-pop__item-name">${esc(g.name || g.id)}</span>
                <span class="mine-add-pop__item-count">${Number(g.count) || 0}</span>
              </button>
            </li>`
              )
              .join("")}</ul>`
          : `<p class="mine-add-pop__empty muted">还没有分组，先新建一个</p>`;

    el.innerHTML = `
      <div class="mine-add-pop__card">
        <header class="mine-add-pop__head">
          <div>
            <strong>添加至分组</strong>
            <p class="mine-add-pop__sub muted">${esc(title)}</p>
          </div>
          <button type="button" class="mine-add-pop__close" data-close="1" aria-label="关闭">×</button>
        </header>
        ${body}
        <form class="mine-add-pop__create" data-create-form="1">
          <input type="text" name="name" maxlength="40" placeholder="新建分组…" autocomplete="off" />
          <button type="submit" class="mine-add-pop__go" title="新建并加入">新建</button>
        </form>
        <p class="mine-add-pop__hint muted">可在「我的」里管理全部分组</p>
      </div>`;
    placeNear(current?.anchor);
    const input = el.querySelector('input[name="name"]');
    if (input && !list.length && !loading) input.focus();
  }

  async function refreshAndRender() {
    render({ loading: true, groups: [] });
    try {
      const groups = await listGroups({ force: true });
      if (!current) return;
      render({ groups });
    } catch (err) {
      if (!current) return;
      render({ error: err.message || String(err) });
    }
  }

  async function pickGroup(groupId, groupName) {
    if (!current || busy) return;
    const { code, name } = current;
    busy = true;
    try {
      const data = await addStock(groupId, code, name);
      const added = Array.isArray(data?.added) ? data.added.length : 0;
      const label = groupName || "分组";
      if (added > 0) toast(`已加入「${label}」`);
      else toast(`已在「${label}」中`, "flat");
      close();
    } catch (err) {
      busy = false;
      toast(err.message || String(err), "err");
      render({ error: err.message || String(err), groups: groupsCache || [] });
    }
  }

  async function onCreate(name) {
    if (!current || busy) return;
    const text = String(name || "").trim();
    if (!text) return;
    busy = true;
    try {
      const group = await createGroup(text);
      const data = await addStock(group.id, current.code, current.name);
      const added = Array.isArray(data?.added) ? data.added.length : 0;
      if (added > 0) toast(`已新建并加入「${group.name || text}」`);
      else toast(`已在「${group.name || text}」中`, "flat");
      close();
    } catch (err) {
      busy = false;
      toast(err.message || String(err), "err");
      await refreshAndRender();
    }
  }

  function onPopClick(ev) {
    if (ev.target.closest("[data-close]")) {
      ev.preventDefault();
      close();
      return;
    }
    const item = ev.target.closest("[data-group-id]");
    if (item) {
      ev.preventDefault();
      void pickGroup(item.dataset.groupId, item.dataset.groupName || "");
    }
  }

  async function open(anchor, { code, name } = {}) {
    const c = String(code || "").trim();
    if (!c) return;
    current = {
      code: c,
      name: String(name || "").trim(),
      anchor: anchor || null,
    };
    busy = false;
    await refreshAndRender();
  }

  function bindRoot(root = document) {
    if (!root || root.__orbitMineAddBound) return;
    root.__orbitMineAddBound = true;
    root.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-add-group]");
      if (!btn || (root !== document && !root.contains(btn))) return;
      ev.preventDefault();
      ev.stopPropagation();
      void open(btn, {
        code: btn.dataset.code || btn.getAttribute("data-add-group") || "",
        name: btn.dataset.name || "",
      });
    });
  }

  document.addEventListener("click", (ev) => {
    const el = document.getElementById(POP_ID);
    if (!el || el.hidden) return;
    if (el.contains(ev.target)) return;
    if (ev.target.closest("[data-add-group]")) return;
    close();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    const el = document.getElementById(POP_ID);
    if (!el || el.hidden) return;
    close();
  });

  document.addEventListener("submit", (ev) => {
    const form = ev.target.closest?.("[data-create-form]");
    if (!form || !document.getElementById(POP_ID)?.contains(form)) return;
    ev.preventDefault();
    const input = form.querySelector('input[name="name"]');
    void onCreate(input?.value || "");
  });

  window.OrbitMineAdd = {
    open,
    close,
    bindRoot,
    buttonHtml,
    toast,
  };
})();
