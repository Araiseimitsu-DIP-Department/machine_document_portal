(() => {
  const shell = document.querySelector("#app-shell");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const refreshButton = document.querySelector("[data-refresh-button]");
  const toast = document.querySelector("[data-toast]");

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

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      refreshButton.disabled = true;
      refreshButton.classList.add("is-loading");
      try {
        const response = await fetch("/api/refresh", { method: "POST" });
        if (!response.ok) throw new Error("refresh failed");
        const result = await response.json();
        showToast(result.message);
        window.setTimeout(() => window.location.reload(), 500);
      } catch (_error) {
        showToast("更新できませんでした。しばらくしてから再度お試しください。", true);
      } finally {
        refreshButton.disabled = false;
        refreshButton.classList.remove("is-loading");
      }
    });
  }
})();
