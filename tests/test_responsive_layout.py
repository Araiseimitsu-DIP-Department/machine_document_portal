from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_portal_templates_expose_mobile_navigation_and_safe_area_viewport() -> None:
    base_template = read_project_file("app/templates/base.html")
    drawing_template = read_project_file("app/templates/drawing_viewer.html")

    assert "viewport-fit=cover" in base_template
    assert "viewport-fit=cover" in drawing_template
    assert 'id="main-navigation"' in base_template
    assert "data-mobile-nav-toggle" in base_template
    assert "data-mobile-nav-close" in base_template
    assert 'aria-controls="main-navigation"' in base_template
    assert "data-mobile-nav-backdrop" in base_template
    assert "mobile-print-attention-count" in base_template
    assert "?v={{ static_assets_version }}" in base_template
    assert "?v={{ static_assets_version }}" in drawing_template


def test_machine_groups_are_responsive_disclosures() -> None:
    dashboard_template = read_project_file("app/templates/index.html")

    assert '<details class="group-column"' in dashboard_template
    assert '<summary class="group-column-header">' in dashboard_template
    assert dashboard_template.count("<details") == dashboard_template.count("</details>")


def test_styles_cover_dynamic_viewports_safe_areas_and_touch_targets() -> None:
    stylesheet = read_project_file("app/static/css/style.css")

    assert "100dvh" in stylesheet
    assert "env(safe-area-inset-top)" in stylesheet
    assert "env(safe-area-inset-right)" in stylesheet
    assert "env(safe-area-inset-bottom)" in stylesheet
    assert "env(safe-area-inset-left)" in stylesheet
    assert ".mobile-nav-open .sidebar" in stylesheet
    assert ".mobile-nav-backdrop[hidden]" in stylesheet
    assert "min-height: 2.75rem" in stylesheet
    assert ".group-column:not([open])" in stylesheet
    assert "touch-action: pan-x pan-y" in stylesheet
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in stylesheet
    assert ".drawing-viewer-body.is-pannable" in stylesheet
    assert ".drawing-viewer-body.is-panning" in stylesheet


def test_client_script_controls_mobile_navigation_groups_and_pinch_zoom() -> None:
    script = read_project_file("app/static/js/app.js")

    assert 'window.matchMedia("(max-width: 680px)")' in script
    assert "setMobileNavState" in script
    assert 'event.key === "Escape"' in script
    assert "applyResponsiveGroupState" in script
    assert '"touchstart"' in script
    assert '"touchmove"' in script
    assert "{ passive: false }" in script
    assert 'dataset.activePage === "dashboard"' in script
    assert "dashboardRevisionPollSeconds * 1000" in script
    assert "refreshDashboardRevision, 10000" not in script
    assert "window.sessionStorage.getItem(drawingViewerZoomStorageKey)" in script
    assert "window.sessionStorage.setItem(drawingViewerZoomStorageKey" in script
    assert "setDrawingViewerZoom(restoredZoom)" in script
    assert '"pointerdown"' in script
    assert '"pointermove"' in script
    assert "drawingViewerBody.scrollLeft" in script
    assert "drawingViewerBody.scrollTop" in script


def test_drawing_viewer_controls_are_consistent_and_support_mouse_panning() -> None:
    drawing_template = read_project_file("app/templates/drawing_viewer.html")

    assert 'class="btn btn-primary"' not in drawing_template
    assert "マウス：ドラッグで移動" in drawing_template
    assert 'draggable="false"' in drawing_template
