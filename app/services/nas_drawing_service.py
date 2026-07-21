from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock


class NasDrawingAccessError(RuntimeError):
    """Raised when the configured NAS drawing directory cannot be accessed."""


class NasDrawingPreviewError(RuntimeError):
    """Raised when a drawing PDF cannot be rendered as an image."""


@dataclass(frozen=True, slots=True)
class CachedDrawingPreview:
    signature: tuple[int, int]
    content: bytes


class NasDrawingService:
    """Locate drawing PDFs whose filename matches a production part number."""

    def __init__(self, drawing_directory: Path | None) -> None:
        self.drawing_directory = drawing_directory

    def find_pdf(self, part_number: str | None) -> Path | None:
        if not part_number or self.drawing_directory is None:
            return None
        filename = self._pdf_filename(part_number)
        if filename is None:
            return None
        candidate = self.drawing_directory / filename
        try:
            return candidate if candidate.is_file() else None
        except OSError as exc:
            raise NasDrawingAccessError("NAS drawing directory is unavailable") from exc

    @staticmethod
    def _pdf_filename(part_number: str) -> str | None:
        filename = part_number
        if not filename.strip() or "/" in filename or "\\" in filename:
            return None
        return filename if filename.lower().endswith(".pdf") else f"{filename}.pdf"


class NasDrawingPreviewService:
    """Render and cache the first PDF page as a JPEG preview."""

    def __init__(
        self, *, cache_size: int = 64, max_cache_bytes: int = 128 * 1024 * 1024
    ) -> None:
        self.cache_size = cache_size
        self.max_cache_bytes = max_cache_bytes
        self._cache: OrderedDict[Path, CachedDrawingPreview] = OrderedDict()
        self._cache_bytes = 0
        self._lock = RLock()
        self._render_locks: dict[Path, Lock] = {}

    def render_first_page(self, drawing_path: Path) -> bytes:
        try:
            stat = drawing_path.stat()
        except OSError as exc:
            raise NasDrawingAccessError("NAS drawing file is unavailable") from exc
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._cache.get(drawing_path)
            if cached and cached.signature == signature:
                self._cache.move_to_end(drawing_path)
                return cached.content
            render_lock = self._render_locks.setdefault(drawing_path, Lock())

        with render_lock:
            with self._lock:
                cached = self._cache.get(drawing_path)
                if cached and cached.signature == signature:
                    self._cache.move_to_end(drawing_path)
                    return cached.content
            try:
                import fitz

                with fitz.open(drawing_path) as document:
                    if document.page_count == 0:
                        raise NasDrawingPreviewError("Drawing PDF has no pages")
                    page = document.load_page(0)
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(1.5, 1.5), alpha=False
                    )
                    content = pixmap.tobytes("jpeg", jpg_quality=85)
            except NasDrawingPreviewError:
                raise
            except Exception as exc:
                raise NasDrawingPreviewError("Drawing PDF preview could not be rendered") from exc

            with self._lock:
                previous = self._cache.pop(drawing_path, None)
                if previous:
                    self._cache_bytes -= len(previous.content)
                self._cache[drawing_path] = CachedDrawingPreview(signature, content)
                self._cache_bytes += len(content)
                while (
                    len(self._cache) > self.cache_size
                    or self._cache_bytes > self.max_cache_bytes
                ):
                    _, evicted = self._cache.popitem(last=False)
                    self._cache_bytes -= len(evicted.content)
        return content
