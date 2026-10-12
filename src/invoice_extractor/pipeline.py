"""High-level helpers that combine extraction, validation and export."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from .config import Settings
from .exporters import export_excel, export_json
from .extractor import ExtractionError, extract_invoice
from .models import Invoice
from .validator import validate_invoice

log = logging.getLogger(__name__)


def collect_pdfs(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into the PDFs they contain (sorted, non-recursive)."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.iterdir() if p.suffix.lower() == ".pdf"))
        elif path.suffix.lower() == ".pdf":
            found.append(path)
        else:
            log.warning("skipping non-PDF path %s", path)
    return found


def process_file(path: Path, settings: Settings) -> Invoice:
    invoice = extract_invoice(path, ocr_enabled=settings.ocr_enabled, ocr_language=settings.ocr_language)
    result = validate_invoice(invoice, tolerance=settings.tolerance)
    if result.is_valid:
        log.info("%s: valid (total %s %s)", path.name, invoice.total, invoice.currency)
    else:
        log.warning("%s: INVALID - %s", path.name, "; ".join(result.errors))
    for warning in result.warnings:
        log.warning("%s: %s", path.name, warning)
    return invoice


def process_files(paths: Iterable[Path], settings: Settings) -> tuple[list[Invoice], dict[str, str]]:
    """Process PDFs; returns (invoices, failures-by-filename)."""
    invoices: list[Invoice] = []
    failures: dict[str, str] = {}
    for path in collect_pdfs(paths):
        try:
            invoices.append(process_file(path, settings))
        except ExtractionError as exc:
            log.error("%s", exc)
            failures[path.name] = str(exc)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
            log.exception("unexpected error while processing %s", path.name)
            failures[path.name] = f"{type(exc).__name__}: {exc}"
    return invoices, failures


def export_all(invoices: list[Invoice], settings: Settings, formats: Iterable[str] = ("excel", "json")) -> list[Path]:
    written: list[Path] = []
    formats = set(formats)
    if "excel" in formats:
        written.append(export_excel(invoices, settings.output_dir / settings.excel_filename))
    if "json" in formats:
        written.append(export_json(invoices, settings.output_dir / settings.json_filename))
    return written
