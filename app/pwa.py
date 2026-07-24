"""PWA および静的アイコン向けのメタデータ。"""

from hashlib import sha256
from pathlib import Path

# アイコン差し替え時はこの値を更新してキャッシュを無効化する。
STATIC_ICONS_VERSION = "1"


def _build_static_assets_version() -> str:
    digest = sha256()
    static_directory = Path(__file__).resolve().parent / "static"
    for relative_path in (
        "css/style.css",
        "js/app.js",
        "js/drawing_viewer.js",
        "manifest.json",
        "vendor/pdfjs/pdf.min.mjs",
        "vendor/pdfjs/pdf.worker.min.mjs",
        "vendor/pdfjs/legacy/pdf.min.mjs",
        "vendor/pdfjs/legacy/pdf.worker.min.mjs",
    ):
        digest.update((static_directory / relative_path).read_bytes())
    return digest.hexdigest()[:12]


STATIC_ASSETS_VERSION = _build_static_assets_version()

PWA_THEME_COLOR = "#1e88e5"
PWA_BACKGROUND_COLOR = "#0d1b2a"
PWA_NAME = "稼働中工程内検査シート"
PWA_SHORT_NAME = "稼働中工程内検査シート"
