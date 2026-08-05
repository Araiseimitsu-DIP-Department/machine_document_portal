const PDFJS_VERSION = "5.7.284";
const PDFJS_BASE_URL = "/static/vendor/pdfjs";
const RERENDER_DELAY_MS = 250;
const RESIZE_DELAY_MS = 150;
const BUTTON_ZOOM_STEP = 25;
const WHEEL_ZOOM_STEP = 10;
const MIN_ZOOM = 50;
// Split View halves the available width, so 300% can be insufficient to inspect
// drawing callouts. Keep rendering from the source PDF and allow up to 800%.
const MAX_ZOOM = 800;

const detectBrowserProfile = () => {
  const userAgent = window.navigator.userAgent;
  const appleMobile = /iPad|iPhone|iPod/.test(userAgent)
    || (
      window.navigator.platform === "MacIntel"
      && window.navigator.maxTouchPoints > 1
    );
  const safari = /Safari/.test(userAgent)
    && !/Chrome|Chromium|CriOS|Edg|EdgiOS|FxiOS|OPiOS|Android/.test(userAgent);
  const coarsePointer = window.matchMedia("(pointer: coarse)").matches;
  const touchDevice = window.navigator.maxTouchPoints > 0 && coarsePointer;
  const compactTouchDevice = touchDevice
    && Math.min(window.screen.width, window.screen.height) < 600;

  if (compactTouchDevice) {
    return {
      name: "compact-mobile",
      useLegacyBuild: appleMobile || safari,
      maxDevicePixelRatio: 1.5,
      maxCanvasSide: 3072,
      maxCanvasPixels: 6_000_000,
      maxImageCanvasBytes: 16_000_000,
    };
  }
  if (touchDevice) {
    return {
      name: "tablet",
      useLegacyBuild: appleMobile || safari,
      // A split tablet viewport needs a higher-resolution source canvas when
      // zoomed in. These limits keep one rendered page below roughly 64 MiB
      // while avoiding the former 10 megapixel downsampling.
      maxDevicePixelRatio: 2,
      maxCanvasSide: 4096,
      maxCanvasPixels: 16_000_000,
      maxImageCanvasBytes: 32_000_000,
    };
  }
  return {
    name: "desktop",
    useLegacyBuild: safari,
    maxDevicePixelRatio: 2,
    maxCanvasSide: 5120,
    maxCanvasPixels: 16_000_000,
    maxImageCanvasBytes: 32_000_000,
  };
};

const viewerBody = document.querySelector("[data-drawing-viewer]");

if (viewerBody) {
  initializeDrawingViewer(viewerBody);
}

async function initializeDrawingViewer(body) {
  const stage = body.querySelector("[data-drawing-viewer-stage]");
  const status = body.querySelector("[data-drawing-viewer-status]");
  const fallbackImage = body.querySelector("[data-drawing-viewer-fallback]");
  const zoomInButton = document.querySelector("[data-drawing-viewer-zoom-in]");
  const zoomOutButton = document.querySelector("[data-drawing-viewer-zoom-out]");
  const zoomResetButton = document.querySelector("[data-drawing-viewer-zoom-reset]");
  let activeCanvas = body.querySelector("[data-drawing-viewer-canvas]");
  if (
    !stage
    || !status
    || !fallbackImage
    || !activeCanvas
    || !zoomInButton
    || !zoomOutButton
    || !zoomResetButton
  ) return;

  const pdfUrl = body.dataset.pdfUrl;
  const previewUrl = body.dataset.previewUrl;
  const debugEnabled = body.dataset.debug === "true";
  const zoomStorageKey = `machine-portal-drawing-zoom:${window.location.pathname}`;
  const viewerStartedAt = performance.now();
  const browserProfile = detectBrowserProfile();
  const pdfAbortController = new AbortController();
  body.dataset.deviceProfile = browserProfile.name;
  body.dataset.pdfjsBuild = browserProfile.useLegacyBuild ? "legacy" : "modern";
  body.setAttribute("aria-busy", "true");

  let pdfjsLib = null;
  let loadingTask = null;
  let pdfDocument = null;
  let pdfPage = null;
  let pageViewport = null;
  let fitScale = 1;
  let renderFitScale = 1;
  let baseCssWidth = 1;
  let baseCssHeight = 1;
  let fallbackBaseCssWidth = 1;
  let drawingZoom = 100;
  let renderTask = null;
  let renderGeneration = 0;
  let rerenderTimer = null;
  let resizeTimer = null;
  let lastZoomOperationAt = null;
  let pinchStartDistance = 0;
  let pinchStartZoom = 100;
  let drawingPan = null;
  let viewerReady = false;
  let usingFallback = false;
  let viewportResizeObserver = null;

  const recordTiming = (name, startedAt) => {
    const elapsed = Math.round((performance.now() - startedAt) * 10) / 10;
    body.dataset[name] = String(elapsed);
    if (debugEnabled) {
      console.debug(`[drawing-viewer] ${name}: ${elapsed}ms`);
    }
    return elapsed;
  };

  const restoredZoom = (() => {
    try {
      const storedValue = window.sessionStorage.getItem(zoomStorageKey);
      if (storedValue === null) return 100;
      const storedZoom = Number(storedValue);
      return Number.isFinite(storedZoom) ? storedZoom : 100;
    } catch (_error) {
      return 100;
    }
  })();

  const clampZoom = (value) => {
    const numericZoom = Number(value);
    return Number.isFinite(numericZoom)
      ? Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(numericZoom)))
      : 100;
  };

  const updateZoomControls = () => {
    zoomResetButton.textContent = `${drawingZoom}%`;
    zoomInButton.disabled = !viewerReady || drawingZoom >= MAX_ZOOM;
    zoomOutButton.disabled = !viewerReady || drawingZoom <= MIN_ZOOM;
  };

  const updatePannableState = () => {
    window.requestAnimationFrame(() => {
      const hasOverflow = body.scrollWidth > body.clientWidth
        || body.scrollHeight > body.clientHeight;
      body.classList.toggle("is-pannable", viewerReady && hasOverflow);
    });
  };

  const contentSize = () => {
    const style = window.getComputedStyle(body);
    const horizontalPadding = Number.parseFloat(style.paddingLeft)
      + Number.parseFloat(style.paddingRight);
    const verticalPadding = Number.parseFloat(style.paddingTop)
      + Number.parseFloat(style.paddingBottom);
    return {
      width: Math.max(1, body.clientWidth - horizontalPadding),
      height: Math.max(1, body.clientHeight - verticalPadding),
    };
  };

  const standaloneContentSize = (available = contentSize()) => {
    const style = window.getComputedStyle(body);
    const horizontalPadding = Number.parseFloat(style.paddingLeft)
      + Number.parseFloat(style.paddingRight);
    const verticalPadding = Number.parseFloat(style.paddingTop)
      + Number.parseFloat(style.paddingBottom);
    const viewerChromeHeight = Math.max(0, window.innerHeight - body.clientHeight);
    return {
      width: Math.max(
        available.width,
        Number(window.screen?.availWidth || window.screen?.width || 0)
          - horizontalPadding,
      ),
      height: Math.max(
        available.height,
        Number(window.screen?.availHeight || window.screen?.height || 0)
          - viewerChromeHeight
          - verticalPadding,
      ),
    };
  };

  const calculateFitScale = () => {
    if (!pageViewport) return;
    const available = contentSize();
    fitScale = Math.min(
      available.width / pageViewport.width,
      available.height / pageViewport.height,
    );

    // Keep the PDF backing canvas at the resolution it would have in a
    // standalone window. Split View may reduce the CSS display size, but it
    // must never reduce the number of source pixels used to draw the page.
    const standalone = standaloneContentSize(available);
    renderFitScale = Math.max(
      fitScale,
      Math.min(
        standalone.width / pageViewport.width,
        standalone.height / pageViewport.height,
      ),
    );
    // 100% means the same physical drawing size as a standalone window.
    // A Split View shows a clipped portion and uses scrolling instead of
    // shrinking the whole drawing to the narrower pane.
    baseCssWidth = Math.max(1, pageViewport.width * renderFitScale);
    baseCssHeight = Math.max(1, pageViewport.height * renderFitScale);
    body.dataset.fitScale = String(Math.round(fitScale * 1000) / 1000);
    body.dataset.renderFitScale = String(
      Math.round(renderFitScale * 1000) / 1000,
    );
  };

  const calculateFallbackBaseCssWidth = () => {
    if (!fallbackImage.complete || fallbackImage.naturalWidth < 1) return;
    const standalone = standaloneContentSize();
    const fallbackFitScale = Math.min(
      standalone.width / fallbackImage.naturalWidth,
      standalone.height / Math.max(1, fallbackImage.naturalHeight),
    );
    fallbackBaseCssWidth = Math.max(
      1,
      fallbackImage.naturalWidth * fallbackFitScale,
    );
  };

  const viewportAnchor = (clientX, clientY) => {
    const rect = body.getBoundingClientRect();
    return {
      x: Math.min(rect.width, Math.max(0, clientX - rect.left)),
      y: Math.min(rect.height, Math.max(0, clientY - rect.top)),
    };
  };

  const centerAnchor = () => ({
    x: body.clientWidth / 2,
    y: body.clientHeight / 2,
  });

  const applyStageGeometry = (anchor = centerAnchor()) => {
    if (usingFallback) {
      fallbackImage.style.width = `${fallbackBaseCssWidth * drawingZoom / 100}px`;
      updatePannableState();
      return;
    }
    const oldScrollWidth = Math.max(1, body.scrollWidth);
    const oldScrollHeight = Math.max(1, body.scrollHeight);
    const relativeX = (body.scrollLeft + anchor.x) / oldScrollWidth;
    const relativeY = (body.scrollTop + anchor.y) / oldScrollHeight;
    const zoomRatio = drawingZoom / 100;

    stage.style.width = `${baseCssWidth * zoomRatio}px`;
    stage.style.height = `${baseCssHeight * zoomRatio}px`;
    activeCanvas.style.width = `${baseCssWidth}px`;
    activeCanvas.style.height = `${baseCssHeight}px`;
    activeCanvas.style.transform = `scale(${zoomRatio})`;

    window.requestAnimationFrame(() => {
      body.scrollLeft = relativeX * body.scrollWidth - anchor.x;
      body.scrollTop = relativeY * body.scrollHeight - anchor.y;
      updatePannableState();
    });
  };

  const cancelScheduledRender = () => {
    if (rerenderTimer !== null) {
      window.clearTimeout(rerenderTimer);
      rerenderTimer = null;
    }
  };

  const cancelActiveRender = () => {
    renderGeneration += 1;
    if (!renderTask) return;
    try {
      renderTask.cancel();
    } catch (_error) {
      // The task may already have completed between the state check and cancel.
    }
    renderTask = null;
  };

  const limitedRenderViewport = (
    zoomRatio,
    outputScaleLimit = browserProfile.maxDevicePixelRatio,
  ) => {
    const outputScale = Math.min(
      Math.max(1, window.devicePixelRatio || 1),
      outputScaleLimit,
    );
    let renderScale = renderFitScale * zoomRatio * outputScale;
    let viewport = pdfPage.getViewport({ scale: renderScale });
    const sideFactor = browserProfile.maxCanvasSide
      / Math.max(viewport.width, viewport.height);
    const pixelFactor = Math.sqrt(
      browserProfile.maxCanvasPixels / (viewport.width * viewport.height),
    );
    const limitFactor = Math.min(1, sideFactor, pixelFactor);
    if (limitFactor < 1) {
      renderScale *= limitFactor;
      viewport = pdfPage.getViewport({ scale: renderScale });
    }
    return { viewport, renderScale };
  };

  const renderPdf = async (
    zoomRatio,
    timingName,
    outputScaleLimit = browserProfile.maxDevicePixelRatio,
  ) => {
    cancelActiveRender();
    const generation = renderGeneration;
    const renderStartedAt = performance.now();
    const nextCanvas = document.createElement("canvas");
    nextCanvas.className = "drawing-viewer-image";
    nextCanvas.dataset.drawingViewerCanvas = "";
    nextCanvas.setAttribute("role", "img");
    nextCanvas.setAttribute("aria-label", activeCanvas.getAttribute("aria-label") || "加工図面");

    const { viewport, renderScale } = limitedRenderViewport(
      zoomRatio,
      outputScaleLimit,
    );
    nextCanvas.width = Math.max(1, Math.floor(viewport.width));
    nextCanvas.height = Math.max(1, Math.floor(viewport.height));
    const context = nextCanvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Canvas context is unavailable");

    const releaseCanvas = (canvas) => {
      canvas.width = 1;
      canvas.height = 1;
    };
    const currentTask = pdfPage.render({
      canvasContext: context,
      viewport,
      background: "rgb(255, 255, 255)",
      intent: "display",
    });
    renderTask = currentTask;
    try {
      await currentTask.promise;
    } catch (error) {
      releaseCanvas(nextCanvas);
      if (error?.name === "RenderingCancelledException") return false;
      throw error;
    } finally {
      if (renderTask === currentTask) renderTask = null;
    }
    if (generation !== renderGeneration) {
      releaseCanvas(nextCanvas);
      return false;
    }

    const currentZoomRatio = drawingZoom / 100;
    nextCanvas.style.width = `${baseCssWidth}px`;
    nextCanvas.style.height = `${baseCssHeight}px`;
    nextCanvas.style.transform = `scale(${currentZoomRatio})`;
    const previousCanvas = activeCanvas;
    previousCanvas.replaceWith(nextCanvas);
    activeCanvas = nextCanvas;
    releaseCanvas(previousCanvas);
    body.dataset.renderScale = String(Math.round(renderScale * 1000) / 1000);
    body.dataset.canvasWidth = String(nextCanvas.width);
    body.dataset.canvasHeight = String(nextCanvas.height);
    stage.hidden = false;
    recordTiming(timingName, renderStartedAt);
    updatePannableState();
    return true;
  };

  const activateJpegFallback = (error) => {
    if (usingFallback) return;
    const wasReady = viewerReady;
    usingFallback = true;
    viewerReady = true;
    body.setAttribute("aria-busy", "false");
    if (!wasReady) drawingZoom = clampZoom(restoredZoom);
    cancelScheduledRender();
    cancelActiveRender();
    stage.hidden = true;
    activeCanvas.width = 1;
    activeCanvas.height = 1;
    status.hidden = false;
    status.classList.add("is-warning");
    status.textContent = "高画質表示を利用できないため、画像表示へ切り替えました。";
    fallbackImage.hidden = false;
    fallbackImage.src = previewUrl;
    fallbackImage.style.width = "100%";
    body.dataset.renderer = "jpeg-fallback";
    console.error("[drawing-viewer] PDF.js rendering failed; using JPEG fallback.", error);
    updateZoomControls();
  };

  const scheduleHighQualityRender = () => {
    if (!viewerReady || usingFallback || !pdfPage) return;
    cancelScheduledRender();
    rerenderTimer = window.setTimeout(async () => {
      rerenderTimer = null;
      try {
        const rendered = await renderPdf(drawingZoom / 100, "rerenderMs");
        if (rendered && lastZoomOperationAt !== null) {
          recordTiming("zoomSettledToReadyMs", lastZoomOperationAt);
          lastZoomOperationAt = null;
        }
      } catch (error) {
        if (error?.name !== "RenderingCancelledException") {
          activateJpegFallback(error);
        }
      }
    }, RERENDER_DELAY_MS);
  };

  const setZoom = (
    nextZoom,
    { anchor = centerAnchor(), scheduleRender = true, persist = true } = {},
  ) => {
    if (!viewerReady) return;
    const clampedZoom = clampZoom(nextZoom);
    const zoomChanged = clampedZoom !== drawingZoom;
    drawingZoom = clampedZoom;
    updateZoomControls();
    if (zoomChanged) {
      lastZoomOperationAt = performance.now();
      cancelScheduledRender();
      cancelActiveRender();
      applyStageGeometry(anchor);
      if (scheduleRender) scheduleHighQualityRender();
    }
    if (persist) {
      try {
        window.sessionStorage.setItem(zoomStorageKey, String(drawingZoom));
      } catch (_error) {
        // Zoom remains available when storage is blocked by browser policy.
      }
    }
  };

  zoomInButton.disabled = true;
  zoomOutButton.disabled = true;
  zoomInButton.addEventListener("click", () => {
    setZoom(drawingZoom + BUTTON_ZOOM_STEP);
  });
  zoomOutButton.addEventListener("click", () => {
    setZoom(drawingZoom - BUTTON_ZOOM_STEP);
  });
  zoomResetButton.addEventListener("click", () => {
    setZoom(100);
  });

  body.addEventListener("wheel", (event) => {
    if (!viewerReady) return;
    event.preventDefault();
    const direction = event.deltaY < 0 ? 1 : -1;
    setZoom(
      drawingZoom + direction * WHEEL_ZOOM_STEP,
      { anchor: viewportAnchor(event.clientX, event.clientY) },
    );
  }, { passive: false });

  const touchDistance = (touches) => Math.hypot(
    touches[0].clientX - touches[1].clientX,
    touches[0].clientY - touches[1].clientY,
  );
  body.addEventListener("touchstart", (event) => {
    if (!viewerReady || event.touches.length !== 2) return;
    pinchStartDistance = touchDistance(event.touches);
    pinchStartZoom = drawingZoom;
  }, { passive: true });
  body.addEventListener("touchmove", (event) => {
    if (
      !viewerReady
      || event.touches.length !== 2
      || pinchStartDistance === 0
    ) return;
    event.preventDefault();
    const midpoint = {
      x: (event.touches[0].clientX + event.touches[1].clientX) / 2,
      y: (event.touches[0].clientY + event.touches[1].clientY) / 2,
    };
    setZoom(
      pinchStartZoom * touchDistance(event.touches) / pinchStartDistance,
      { anchor: viewportAnchor(midpoint.x, midpoint.y) },
    );
  }, { passive: false });
  body.addEventListener("touchend", (event) => {
    if (event.touches.length < 2) pinchStartDistance = 0;
  }, { passive: true });

  body.addEventListener("pointerdown", (event) => {
    if (
      !viewerReady
      || event.pointerType !== "mouse"
      || event.button !== 0
      || !body.classList.contains("is-pannable")
    ) return;
    drawingPan = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      scrollLeft: body.scrollLeft,
      scrollTop: body.scrollTop,
    };
    body.setPointerCapture(event.pointerId);
    body.classList.add("is-panning");
    event.preventDefault();
  });
  body.addEventListener("pointermove", (event) => {
    if (!drawingPan || event.pointerId !== drawingPan.pointerId) return;
    body.scrollLeft = drawingPan.scrollLeft - (event.clientX - drawingPan.clientX);
    body.scrollTop = drawingPan.scrollTop - (event.clientY - drawingPan.clientY);
  });
  const stopDrawingPan = (event) => {
    if (!drawingPan || event.pointerId !== drawingPan.pointerId) return;
    if (body.hasPointerCapture(event.pointerId)) {
      body.releasePointerCapture(event.pointerId);
    }
    drawingPan = null;
    body.classList.remove("is-panning");
  };
  body.addEventListener("pointerup", stopDrawingPan);
  body.addEventListener("pointercancel", stopDrawingPan);

  fallbackImage.addEventListener("load", () => {
    calculateFallbackBaseCssWidth();
    applyStageGeometry();
    updatePannableState();
  });
  fallbackImage.addEventListener("error", () => {
    status.hidden = false;
    status.classList.add("is-error");
    status.textContent = "加工図面を表示できませんでした。";
    body.classList.remove("is-pannable");
  });

  const redrawForViewportSizeChange = () => {
    if (!viewerReady) {
      updatePannableState();
      return;
    }
    if (usingFallback) {
      calculateFallbackBaseCssWidth();
      applyStageGeometry();
      return;
    }
    if (!pageViewport) return;
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      calculateFitScale();
      applyStageGeometry();
      cancelActiveRender();
      scheduleHighQualityRender();
    }, RESIZE_DELAY_MS);
  };

  // On iPadOS, putting a browser window into Split View can change the element
  // size without a reliable window resize event. Observe the actual viewport so
  // the PDF is always rerendered at the new window's device-pixel resolution.
  if ("ResizeObserver" in window) {
    viewportResizeObserver = new ResizeObserver(redrawForViewportSizeChange);
    viewportResizeObserver.observe(body);
  }
  window.addEventListener("resize", redrawForViewportSizeChange);
  window.visualViewport?.addEventListener("resize", redrawForViewportSizeChange);

  window.addEventListener("pagehide", () => {
    pdfAbortController.abort();
    cancelScheduledRender();
    cancelActiveRender();
    window.clearTimeout(resizeTimer);
    viewportResizeObserver?.disconnect();
    window.visualViewport?.removeEventListener(
      "resize",
      redrawForViewportSizeChange,
    );
    if (pdfDocument) {
      pdfDocument.destroy();
    } else if (loadingTask) {
      loadingTask.destroy();
    }
    activeCanvas.width = 1;
    activeCanvas.height = 1;
  }, { once: true });

  try {
    const moduleStartedAt = performance.now();
    const pdfjsBuildPath = browserProfile.useLegacyBuild ? "/legacy" : "";
    pdfjsLib = await import(
      `${PDFJS_BASE_URL}${pdfjsBuildPath}/pdf.min.mjs?v=${PDFJS_VERSION}`
    );
    recordTiming("pdfJsModuleMs", moduleStartedAt);
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      `${PDFJS_BASE_URL}${pdfjsBuildPath}/pdf.worker.min.mjs?v=${PDFJS_VERSION}`;

    const pdfLoadStartedAt = performance.now();
    const pdfFetchStartedAt = performance.now();
    const pdfResponse = await fetch(pdfUrl, {
      headers: { "Accept": "application/pdf" },
      cache: "default",
      credentials: "same-origin",
      signal: pdfAbortController.signal,
    });
    if (!pdfResponse.ok) {
      throw new Error(`PDF request failed with status ${pdfResponse.status}`);
    }
    const pdfData = await pdfResponse.arrayBuffer();
    recordTiming("pdfFetchMs", pdfFetchStartedAt);
    const pdfInitStartedAt = performance.now();
    loadingTask = pdfjsLib.getDocument({
      data: pdfData,
      cMapUrl: `${PDFJS_BASE_URL}/cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `${PDFJS_BASE_URL}/standard_fonts/`,
      wasmUrl: `${PDFJS_BASE_URL}/wasm/`,
      canvasMaxAreaInBytes: browserProfile.maxImageCanvasBytes,
    });
    pdfDocument = await loadingTask.promise;
    recordTiming("pdfInitMs", pdfInitStartedAt);
    recordTiming("pdfFetchAndInitMs", pdfLoadStartedAt);

    const pageLoadStartedAt = performance.now();
    pdfPage = await pdfDocument.getPage(1);
    pageViewport = pdfPage.getViewport({ scale: 1 });
    calculateFitScale();
    recordTiming("firstPageLoadMs", pageLoadStartedAt);

    // Render the first frame at the display's full pixel density as well.
    // This avoids a low-resolution frame remaining visible in a new Split View
    // window before the deferred high-quality redraw has a chance to run.
    const initialRendered = await renderPdf(1, "initialRenderMs");
    if (!initialRendered) throw new Error("Initial PDF render was cancelled");
    viewerReady = true;
    body.setAttribute("aria-busy", "false");
    body.dataset.renderer = "pdfjs";
    status.hidden = true;
    updateZoomControls();
    applyStageGeometry();
    if (clampZoom(restoredZoom) !== 100) {
      setZoom(restoredZoom);
    } else {
      drawingZoom = 100;
      updateZoomControls();
      lastZoomOperationAt = performance.now();
      scheduleHighQualityRender();
    }
    recordTiming("viewerReadyMs", viewerStartedAt);
  } catch (error) {
    if (
      error?.name !== "RenderingCancelledException"
      && error?.name !== "AbortError"
    ) {
      activateJpegFallback(error);
    }
  }
}
