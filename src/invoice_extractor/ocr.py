"""Optional OCR fallback for scanned (image-only) invoices.

Not required for the bundled samples. To enable it:

1. Install the Tesseract binary (https://github.com/tesseract-ocr/tesseract).
2. ``pip install pytesseract``
3. Set ``ocr.enabled: true`` in ``config.yaml`` (or ``INVOICE_OCR_ENABLED=true``).

Pages are rasterised with pdfplumber (via pypdfium2, already a dependency), so no
poppler/pdf2image install is needed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

log = logging.getLogger(__name__)


class OCRUnavailableError(RuntimeError):
    """Raised when OCR is requested but pytesseract/Tesseract is not installed."""


def ocr_pdf(path: Path, *, language: str = "eng", resolution: int = 300) -> str:
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise OCRUnavailableError("OCR requested but pytesseract is not installed (pip install pytesseract)") from exc

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            image = page.to_image(resolution=resolution).original
            log.debug("OCR page %d of %s", number, path.name)
            pages.append(pytesseract.image_to_string(image, lang=language))
    return "\n".join(pages)
