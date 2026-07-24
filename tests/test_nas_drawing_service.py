from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers import api
from app.schemas.dashboard import MachineCard
from app.services.memory_store import MemoryDashboardStore
from app.services.nas_drawing_service import NasDrawingPreviewService, NasDrawingService


def make_pdf(path: Path) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Drawing preview")
    document.save(path)
    document.close()


def test_nas_drawing_service_finds_a_pdf_by_exact_part_number(tmp_path: Path) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    service = NasDrawingService(tmp_path)

    assert service.find_pdf("AB-100") == drawing
    assert service.find_pdf("AB-100.pdf") == drawing
    assert service.find_pdf("missing") is None
    assert service.find_pdf("../AB-100") is None
    assert service.find_pdf(" AB-100 ") is None


def test_drawing_endpoint_renders_only_the_current_machine_drawing(
    tmp_path: Path, monkeypatch
) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    settings = Settings(
        nas_drawing_directory=tmp_path,
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)
    store.replace_dashboard(
        [MachineCard(machine_id="A-1", group_name="A", machine_number=1, part_number="AB-100")]
    )
    monkeypatch.setattr(api, "get_memory_store", lambda: store)

    response = api.preview_drawing("A-1", settings)

    assert response.media_type == "image/jpeg"
    assert response.body.startswith(b"\xff\xd8")


def test_pdf_endpoint_streams_current_drawing_with_cache_and_range_headers(
    tmp_path: Path, monkeypatch
) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    settings = Settings(
        nas_drawing_directory=tmp_path,
        dashboard_snapshot_path=tmp_path / "dashboard.json",
    )
    store = MemoryDashboardStore(settings)
    store.replace_dashboard(
        [
            MachineCard(
                machine_id="A-1",
                group_name="A",
                machine_number=1,
                part_number="AB-100",
            )
        ]
    )
    monkeypatch.setattr(api, "get_memory_store", lambda: store)
    test_app = FastAPI()
    test_app.include_router(api.router)
    test_app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(test_app) as client:
        response = client.get("/api/drawings/A-1/pdf")
        range_response = client.get(
            "/api/drawings/A-1/pdf", headers={"Range": "bytes=0-4"}
        )
        missing_response = client.get("/api/drawings/not-found/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.headers["accept-ranges"] == "bytes"
    assert "etag" in response.headers
    assert "last-modified" in response.headers
    assert response.headers["content-disposition"].startswith("inline;")
    assert "AB-100.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    assert range_response.status_code == 206
    assert range_response.headers["content-range"].startswith("bytes 0-4/")
    assert range_response.content == response.content[:5]
    assert missing_response.status_code == 404


def test_preview_service_caches_the_rendered_first_page(tmp_path: Path) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    service = NasDrawingPreviewService()

    first = service.render_first_page(drawing)
    second = service.render_first_page(drawing)

    assert first.startswith(b"\xff\xd8")
    assert second is first
