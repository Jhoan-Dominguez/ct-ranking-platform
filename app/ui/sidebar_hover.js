// Expande la barra lateral al pasar el mouse por el borde izquierdo cuando está oculta, y la
// vuelve a ocultar al salir de ella. Sólo actúa sobre una apertura hecha por hover: si el usuario
// abre el menú con el botón ">>" queda fijo como siempre.
//
// Usa los botones nativos de Streamlit (expandir/colapsar) para que su estado interno, incluido
// el guardado en localStorage, se mantenga coherente. Selectores verificados en Streamlit 1.66.
(() => {
  if (window.__ctSidebarHover) return; // el script se re-ejecuta en cada rerun
  window.__ctSidebarHover = true;
  // Sin mouse (pantallas táctiles) no hay hover.
  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

  const HOT_ZONE_PX = 16;
  const CLOSE_DELAY_MS = 400;

  const sidebar = () => document.querySelector('section[data-testid="stSidebar"]');
  const isCollapsed = () => sidebar()?.getAttribute("data-collapsed") === "true";
  const expandButton = () => document.querySelector('[data-testid="stExpandSidebarButton"]');
  const collapseButton = () =>
    document.querySelector('[data-testid="stSidebarCollapseButton"] button');

  let openedByHover = false;
  let closeTimer = null;

  const zone = document.createElement("div");
  zone.id = "ct-sidebar-hover-zone";
  Object.assign(zone.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: `${HOT_ZONE_PX}px`,
    height: "100vh",
    zIndex: "999990",
    background: "transparent",
    display: "none",
  });
  document.body.appendChild(zone);

  const cancelClose = () => {
    clearTimeout(closeTimer);
    closeTimer = null;
  };

  const scheduleClose = () => {
    if (!openedByHover || closeTimer) return;
    closeTimer = setTimeout(() => {
      closeTimer = null;
      if (openedByHover && !isCollapsed()) collapseButton()?.click();
      openedByHover = false;
    }, CLOSE_DELAY_MS);
  };

  const sync = () => {
    const collapsed = isCollapsed();
    zone.style.display = collapsed && sidebar() ? "block" : "none";
    if (collapsed) {
      openedByHover = false;
      cancelClose();
    }
  };

  zone.addEventListener("mouseenter", () => {
    if (!isCollapsed()) return;
    const button = expandButton();
    if (!button) return;
    openedByHover = true;
    button.click();
  });

  // El mouse sale de la barra lateral (hacia el contenido o fuera de la ventana).
  document.addEventListener("mouseover", (event) => {
    if (!openedByHover) return;
    const sb = sidebar();
    if (sb?.contains(event.target) || zone.contains(event.target)) cancelClose();
    else scheduleClose();
  });
  document.documentElement.addEventListener("mouseleave", scheduleClose);

  // Mantiene la zona activa sólo mientras el menú está oculto.
  new MutationObserver(sync).observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["data-collapsed"],
  });
  sync();
})();
