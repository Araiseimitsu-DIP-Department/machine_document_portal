from pathlib import Path

from app.config import Settings
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


def test_drawing_endpoint_renders_only_the_current_machine_drawing(
    tmp_path: Path, monkeypatch
) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    settings = Settings(nas_drawing_directory=tmp_path)
    store = MemoryDashboardStore(settings)
    store.replace_dashboard(
        [MachineCard(machine_id="A-1", group_name="A", machine_number=1, part_number="AB-100")]
    )
    monkeypatch.setattr(api, "get_memory_store", lambda: store)

    response = api.preview_drawing("A-1", settings)

    assert response.media_type == "image/jpeg"
    assert response.body.startswith(b"\xff\xd8")


def test_preview_service_caches_the_rendered_first_page(tmp_path: Path) -> None:
    drawing = tmp_path / "AB-100.pdf"
    make_pdf(drawing)
    service = NasDrawingPreviewService()

    first = service.render_first_page(drawing)
    second = service.render_first_page(drawing)

    assert first.startswith(b"\xff\xd8")
    assert second is first
