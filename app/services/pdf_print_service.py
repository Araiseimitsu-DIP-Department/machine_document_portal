from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PdfPrintError(RuntimeError):
    """A PDF could not be submitted to the configured Windows printer."""


class PdfPrinter(Protocol):
    def print_pdf(self, pdf_path: Path) -> None: ...


class RawPdfPrinter:
    """Submit PDF bytes using the RAW workflow from the existing production script."""

    def __init__(self, printer_name: str) -> None:
        self.printer_name = printer_name

    def print_pdf(self, pdf_path: Path) -> None:
        try:
            import win32print
        except ImportError as exc:
            raise PdfPrintError("pywin32 is not installed") from exc

        printer = None
        document_started = False
        page_started = False
        try:
            content = pdf_path.read_bytes()
            printer = win32print.OpenPrinter(self.printer_name)
            win32print.StartDocPrinter(
                printer,
                1,
                (f"翌営業日加工図_{pdf_path.stem}", None, "RAW"),
            )
            document_started = True
            win32print.StartPagePrinter(printer)
            page_started = True
            win32print.WritePrinter(printer, content)
            win32print.EndPagePrinter(printer)
            page_started = False
            win32print.EndDocPrinter(printer)
            document_started = False
        except Exception as exc:
            raise PdfPrintError(f"PDF print submission failed: {pdf_path.name}") from exc
        finally:
            if printer is not None:
                if page_started:
                    try:
                        win32print.EndPagePrinter(printer)
                    except Exception:
                        pass
                if document_started:
                    try:
                        win32print.EndDocPrinter(printer)
                    except Exception:
                        pass
                try:
                    win32print.ClosePrinter(printer)
                except Exception:
                    pass
