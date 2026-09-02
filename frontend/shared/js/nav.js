(() => {
  const path = location.pathname.replace(/\.html$/, "") || "/";
  const key =
    path === "/" || path === ""
      ? "industry"
      : path.startsWith("/market")
        ? "market"
        : path.startsWith("/steep")
          ? "steep"
          : path.startsWith("/list")
            ? "list"
            : "";
  document.querySelectorAll(".app-rail-link").forEach((link) => {
    const active = !!key && link.dataset.nav === key;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
})();
