(() => {
  const shell = document.querySelector("#app-shell");
  const sidebar = document.querySelector("#main-navigation");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const mobileNavToggle = document.querySelector("[data-mobile-nav-toggle]");
  const mobileNavClose = document.querySelector("[data-mobile-nav-close]");
  const mobileNavBackdrop = document.querySelector("[data-mobile-nav-backdrop]");
  const refreshButton = document.querySelector("[data-refresh-button]");
  const toast = document.querySelector("[data-toast]");
  const initialDashboardRevision = document.body.dataset.dashboardRevision || "";
  const dashboardRevisionPollSeconds = Number.parseInt(
    document.body.dataset.dashboardRevisionPollSeconds || "0",
    10,
  );
  const groupColumns = Array.from(document.querySelectorAll("details.group-column"));
  const mobileViewport = window.matchMedia("(max-width: 680px)");
  const printSubmitForms = document.querySelectorAll("[data-print-submit-form]");
  let mobileGroupOpenStates = null;
  let userOperationInProgress = false;
  let reloadPending = false;

  const requestPageReload = () => {
    if (userOperationInProgress) {
      reloadPending = true;
      return;
    }
    window.location.reload();
  };

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

  const setMobileNavState = (open, restoreFocus = false) => {
    if (!sidebar || !mobileNavToggle || !mobileNavBackdrop) return;
    const shouldOpen = mobileViewport.matches && open;
    document.body.classList.toggle("mobile-nav-open", shouldOpen);
    mobileNavToggle.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    mobileNavToggle.setAttribute("aria-label", shouldOpen ? "メニューを閉じる" : "メニューを開く");
    mobileNavBackdrop.hidden = !shouldOpen;

    if (mobileViewport.matches) {
      sidebar.setAttribute("aria-hidden", shouldOpen ? "false" : "true");
      sidebar.inert = !shouldOpen;
    } else {
      sidebar.removeAttribute("aria-hidden");
      sidebar.inert = false;
    }

    if (shouldOpen) {
      mobileNavClose?.focus();
    } else if (restoreFocus && mobileViewport.matches) {
      mobileNavToggle.focus();
    }
  };

  const applyResponsiveGroupState = (isMobile) => {
    if (!groupColumns.length) return;
    if (isMobile) {
      const states = mobileGroupOpenStates || groupColumns.map((_group, index) => index === 0);
      groupColumns.forEach((group, index) => { group.open = Boolean(states[index]); });
      return;
    }
    groupColumns.forEach((group) => { group.open = true; });
  };

  if (mobileNavToggle && sidebar && mobileNavBackdrop) {
    setMobileNavState(false);
    mobileNavToggle.addEventListener("click", () => {
      setMobileNavState(mobileNavToggle.getAttribute("aria-expanded") !== "true");
    });
    mobileNavClose?.addEventListener("click", () => setMobileNavState(false, true));
    mobileNavBackdrop.addEventListener("click", () => setMobileNavState(false, true));
    sidebar.querySelectorAll("a.nav-item").forEach((link) => {
      link.addEventListener("click", () => setMobileNavState(false));
    });
  }

  const handleMobileViewportChange = (event) => {
    if (!event.matches) {
      mobileGroupOpenStates = groupColumns.map((group) => group.open);
    }
    setMobileNavState(false);
    applyResponsiveGroupState(event.matches);
  };

  applyResponsiveGroupState(mobileViewport.matches);
  if (typeof mobileViewport.addEventListener === "function") {
    mobileViewport.addEventListener("change", handleMobileViewportChange);
  } else {
    mobileViewport.addListener(handleMobileViewportChange);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("mobile-nav-open")) {
      setMobileNavState(false, true);
      return;
    }
    if (
      event.key !== "Tab"
      || !sidebar
      || !document.body.classList.contains("mobile-nav-open")
    ) return;

    const focusable = Array.from(
      sidebar.querySelectorAll("a[href], button:not([disabled])")
    ).filter((element) => !element.hidden && element.getClientRects().length > 0);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  const showToast = (message, isError = false) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("toast-error", isError);
    toast.hidden = false;
    window.setTimeout(() => { toast.hidden = true; }, 4000);
  };

  const refreshDashboard = async () => {
    if (!refreshButton || refreshButton.disabled) return;
    userOperationInProgress = true;
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
      window.setTimeout(requestPageReload, 500);
    } catch (_error) {
      showToast("更新できませんでした。しばらくしてから再度お試しください。", true);
    } finally {
      userOperationInProgress = false;
      refreshButton.disabled = false;
      refreshButton.classList.remove("is-loading");
      if (reloadPending) requestPageReload();
    }
  };

  if (refreshButton) {
    refreshButton.addEventListener("click", refreshDashboard);
  }

  printSubmitForms.forEach((form) => {
    form.addEventListener("submit", () => {
      userOperationInProgress = true;
      const button = form.querySelector("[data-print-submit]");
      if (!button) return;
      button.disabled = true;
      button.textContent = "印刷しています…";
    });
  });

  const refreshPrintAttention = async () => {
    try {
      const response = await fetch("/api/printing/attention", {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      if (!response.ok) return;
      const result = await response.json();
      const currentRequired = document.body.dataset.hasPrintAttention === "true";
      const currentCount = Number.parseInt(document.body.dataset.printAttentionCount || "0", 10);
      if (Boolean(result.required) !== currentRequired || Number(result.count) !== currentCount) {
        requestPageReload();
      }
    } catch (_error) {
      // Printing continues on the server; a temporary status-check failure needs no user alert.
    }
  };
  if (document.body.hasAttribute("data-has-print-attention")) {
    window.setInterval(refreshPrintAttention, 60000);
  }

  const refreshDashboardRevision = async () => {
    try {
      const response = await fetch("/api/dashboard/revision", {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      if (!response.ok) return;
      const result = await response.json();
      const latestRevision = result.updated_at || "";
      if (latestRevision !== initialDashboardRevision) requestPageReload();
    } catch (_error) {
      // A later poll will detect the completed update; users need no error message.
    }
  };
  if (
    document.body.dataset.activePage === "dashboard"
    && Number.isFinite(dashboardRevisionPollSeconds)
    && dashboardRevisionPollSeconds > 0
  ) {
    window.setInterval(
      refreshDashboardRevision,
      dashboardRevisionPollSeconds * 1000,
    );
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshDashboardRevision();
    });
  }

})();
