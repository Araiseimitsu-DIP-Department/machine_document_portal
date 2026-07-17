(() => {
  const shell = document.querySelector("#app-shell");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const refreshButton = document.querySelector("[data-refresh-button]");
  const toast = document.querySelector("[data-toast]");
  const autoRefreshSeconds = Number.parseInt(document.body.dataset.autoRefreshSeconds || "0", 10);
  const drawingPreviewDialog = document.querySelector("[data-drawing-preview-dialog]");
  const drawingPreviewImage = document.querySelector("[data-drawing-preview-image]");
  const drawingPreviewTitle = document.querySelector("[data-drawing-preview-title]");
  const drawingPreviewClose = document.querySelector("[data-drawing-preview-close]");
  const drawingPreviewZoomIn = document.querySelector("[data-drawing-preview-zoom-in]");
  const drawingPreviewZoomOut = document.querySelector("[data-drawing-preview-zoom-out]");
  const drawingPreviewZoomReset = document.querySelector("[data-drawing-preview-zoom-reset]");
  let drawingPreviewZoom = 100;

  const setSidebarState = (collapsed) => {
    if (!shell || !toggle) return;
    shell.classList.toggle("sidebar-collapsed", collapsed);
    const label = collapsed ? "サイドバーを開く" : "サイドバーを折りたたむ";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
    localStorage.setItem("machine-portal-sidebar", collapsed ? "collapsed" : "open");
  };

  if (toggle) {
    setSidebarState(localStorage.getItem("machine-portal-sidebar") === "collapsed");
    toggle.addEventListener("click", () => {
      setSidebarState(!shell.classList.contains("sidebar-collapsed"));
    });
  }

  const showToast = (message, isError = false) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("toast-error", isError);
    toast.hidden = false;
    window.setTimeout(() => { toast.hidden = true; }, 4000);
  };

  const refreshDashboard = async () => {
    if (!refreshButton || refreshButton.disabled) return;
    refreshButton.disabled = true;
    refreshButton.classList.add("is-loading");
    try {
      const response = await fetch("/api/refresh", { method: "POST" });
      if (!response.ok) throw new Error("refresh failed");
      const result = await response.json();
      if (!result.ok) {
        showToast(result.message, true);
        return;
      }
      showToast(result.message);
      window.setTimeout(() => window.location.reload(), 500);
    } catch (_error) {
      showToast("更新できませんでした。しばらくしてから再度お試しください。", true);
    } finally {
      refreshButton.disabled = false;
      refreshButton.classList.remove("is-loading");
    }
  };

  if (refreshButton) {
    refreshButton.addEventListener("click", refreshDashboard);
  }

  if (refreshButton && Number.isFinite(autoRefreshSeconds) && autoRefreshSeconds > 0) {
    window.setInterval(() => window.location.reload(), autoRefreshSeconds * 1000);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-drawing-preview]");
    if (!link || !drawingPreviewDialog || !drawingPreviewImage) return;
    event.preventDefault();
    drawingPreviewImage.src = link.href;
    drawingPreviewImage.alt = link.getAttribute("aria-label") || "加工図プレビュー";
    if (drawingPreviewTitle) drawingPreviewTitle.textContent = drawingPreviewImage.alt;
    drawingPreviewZoom = 100;
    drawingPreviewImage.style.width = "100%";
    drawingPreviewDialog.showModal();
  });

  drawingPreviewClose?.addEventListener("click", () => drawingPreviewDialog.close());
  const setDrawingPreviewZoom = (nextZoom) => {
    if (!drawingPreviewImage) return;
    drawingPreviewZoom = Math.min(300, Math.max(50, nextZoom));
    drawingPreviewImage.style.width = `${drawingPreviewZoom}%`;
    if (drawingPreviewZoomReset) drawingPreviewZoomReset.textContent = `${drawingPreviewZoom}%`;
  };
  drawingPreviewZoomIn?.addEventListener("click", () => setDrawingPreviewZoom(drawingPreviewZoom + 25));
  drawingPreviewZoomOut?.addEventListener("click", () => setDrawingPreviewZoom(drawingPreviewZoom - 25));
  drawingPreviewZoomReset?.addEventListener("click", () => setDrawingPreviewZoom(100));
  drawingPreviewDialog?.addEventListener("close", () => {
    if (drawingPreviewImage) {
      drawingPreviewImage.removeAttribute("src");
      drawingPreviewImage.style.removeProperty("width");
    }
    if (drawingPreviewZoomReset) drawingPreviewZoomReset.textContent = "100%";
  });
})();
