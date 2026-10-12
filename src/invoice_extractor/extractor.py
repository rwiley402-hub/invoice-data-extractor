"""Turn invoice PDFs into structured :class:`~invoice_extractor.models.Invoice` objects.

Strategy
--------
1. Read the text layer (and any ruled tables) with pdfplumber.
2. If there is no text layer the PDF is probably a scan; optionally fall back to OCR.
3. Header fields (number, dates, vendor) are found with label-anchored regexes.
4. Line items come from a detected table when one exists, otherwise from text rows
   between the column-header line and the ``Subtotal`` line.
5. Totals are read from the block that starts at ``Subtotal``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pdfplumber

from .models import Invoice, LineItem
from .parsing import (
    DATE_PATTERN,
    MONEY_PATTERN,
    ParseError,
    detect_currency,
    parse_amount,
    parse_date,
    parse_quantity,
)

log = logging.getLogger(__name__)

QTY = r"\d+(?:[.,]\d+)?"
MONEY = MONEY_PATTERN

INVOICE_NUMBER_RE = re.compile(
    r"Invoice\s*(?:Number|No\.?|#)\s*[:#]?\s*(?P<value>[A-Z0-9][A-Z0-9/_-]*\d[A-Z0-9/_-]*)",
    re.IGNORECASE,
)
ISSUE_DATE_RES = (
    re.compile(rf"(?:Invoice\s+Date|Issue\s+Date|Date\s+of\s+Issue)\s*:?\s*(?P<value>{DATE_PATTERN})", re.IGNORECASE),
    re.compile(rf"(?<!Due )(?<![A-Za-z])Date\s*:?\s*(?P<value>{DATE_PATTERN})", re.IGNORECASE),
)
DUE_DATE_RE = re.compile(rf"(?:Due\s+Date|Payment\s+due|Due)\s*:?\s*(?P<value>{DATE_PATTERN})", re.IGNORECASE)
FROM_RE = re.compile(r"^\s*(?:From|Vendor|Supplier)\s*:\s*(?P<value>.+?)(?:\s+To:.*)?$", re.IGNORECASE | re.MULTILINE)

SUBTOTAL_RE = re.compile(rf"\bSub-?\s?total\b\s*:?\s*(?P<value>{MONEY})", re.IGNORECASE)
TAX_RE = re.compile(
    rf"(?P<label>(?:[A-Za-z]+\s+)?(?:Tax|VAT|GST|HST|MwSt\.?))\s*\(?\s*(?P<rate>{QTY})?\s*%?\s*\)?\s*:?\s*(?P<value>{MONEY})",
    re.IGNORECASE,
)
SHIPPING_RE = re.compile(rf"\b(?:Shipping|Freight|Delivery)(?:\s*&\s*Handling)?\s*:?\s*(?P<value>{MONEY})\s*$",
                         re.IGNORECASE | re.MULTILINE)
TOTAL_RE = re.compile(
    rf"(?<![A-Za-z])(?:Grand\s+Total|Total\s+Due|Amount\s+Due|Balance\s+Due|Total)\s*(?:\([A-Z]{{3}}\))?\s*:?\s*(?P<value>{MONEY})",
    re.IGNORECASE,
)

ITEM_QTY_LAST_RE = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>{QTY})\s+(?P<unit>{MONEY})\s+(?P<amount>{MONEY})\s*$")
ITEM_QTY_FIRST_RE = re.compile(rf"^(?P<qty>{QTY})\s+(?P<desc>.+?)\s+(?P<unit>{MONEY})\s+(?P<amount>{MONEY})\s*$")
ITEM_HEADER_RE = re.compile(r"\b(description|item)\b.*\b(amount|total)\b", re.IGNORECASE)

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "description": ("description", "item", "service", "details"),
    "quantity": ("qty", "quantity", "hours", "units"),
    "unit_price": ("unit price", "rate", "price", "unit cost"),
    "amount": ("amount", "line total", "total", "ext. price"),
}


class ExtractionError(RuntimeError):
    """Raised when a PDF cannot be turned into an invoice at all."""


@dataclass
class RawDocument:
    text: str
    tables: list[list[list[str | None]]]
    method: str = "text"


# --------------------------------------------------------------------------- reading

def read_pdf(path: Path, *, ocr_enabled: bool = False, ocr_language: str = "eng") -> RawDocument:
    """Read the text layer and ruled tables of a PDF (falls back to OCR if enabled)."""
    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        tables = [table for page in pdf.pages for table in page.extract_tables()]
    if text.strip():
        return RawDocument(text=text, tables=tables)
    if not ocr_enabled:
        raise ExtractionError(
            f"{path.name}: no text layer found (scanned image?). Enable OCR in config.yaml to process it."
        )
    from .ocr import ocr_pdf  # imported lazily so pytesseract stays optional

    log.info("%s: no text layer, running OCR", path.name)
    return RawDocument(text=ocr_pdf(path, language=ocr_language), tables=[], method="ocr")


# --------------------------------------------------------------------------- header fields

def _first(regex: re.Pattern[str], text: str) -> str | None:
    match = regex.search(text)
    return match.group("value").strip() if match else None


def extract_vendor(text: str) -> str | None:
    explicit = _first(FROM_RE, text)
    if explicit:
        return explicit
    for line in text.splitlines():
        candidate = re.sub(r"\b(?:TAX\s+)?INVOICE\b", "", line, flags=re.IGNORECASE).strip(" :-|")
        if candidate and not re.match(r"^(?:Invoice|Date|Bill|Page)\b", candidate, re.IGNORECASE):
            return candidate
    return None


def _safe_date(raw: str | None, field_name: str, source: str):
    if raw is None:
        return None
    try:
        return parse_date(raw)
    except ParseError:
        log.warning("%s: could not parse %s %r", source, field_name, raw)
        return None


# --------------------------------------------------------------------------- line items

def _map_columns(header: list[str | None]) -> dict[str, int] | None:
    mapping: dict[str, int] = {}
    normalised = [(cell or "").strip().lower() for cell in header]
    for field_name, aliases in _HEADER_ALIASES.items():
        for idx, cell in enumerate(normalised):
            if idx in mapping.values():
                continue
            if any(cell == alias or cell.startswith(alias) for alias in aliases):
                mapping[field_name] = idx
                break
    return mapping if len(mapping) == 4 else None


def items_from_tables(tables: list[list[list[str | None]]]) -> list[LineItem]:
    for table in tables:
        if not table:
            continue
        columns = _map_columns(table[0])
        if columns is None:
            continue
        items: list[LineItem] = []
        for row in table[1:]:
            try:
                items.append(LineItem(
                    description=re.sub(r"\s+", " ", row[columns["description"]] or "").strip(),
                    quantity=parse_quantity(row[columns["quantity"]] or ""),
                    unit_price=parse_amount(row[columns["unit_price"]] or ""),
                    amount=parse_amount(row[columns["amount"]] or ""),
                ))
            except (ParseError, IndexError):
                log.debug("skipping non-item table row: %r", row)
        if items:
            return items
    return []


def _item_lines(text: str) -> list[str]:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if ITEM_HEADER_RE.search(line)), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if SUBTOTAL_RE.search(lines[i])), len(lines))
    return lines[start + 1:end]


def items_from_text(text: str) -> list[LineItem]:
    items: list[LineItem] = []
    for line in _item_lines(text):
        for regex in (ITEM_QTY_LAST_RE, ITEM_QTY_FIRST_RE):
            match = regex.match(line.strip())
            if not match:
                continue
            try:
                item = LineItem(
                    description=match.group("desc").strip(),
                    quantity=parse_quantity(match.group("qty")),
                    unit_price=parse_amount(match.group("unit")),
                    amount=parse_amount(match.group("amount")),
                )
            except ParseError:
                continue
            items.append(item)
            break
    return items


# --------------------------------------------------------------------------- totals

def _totals_block(text: str) -> str:
    match = SUBTOTAL_RE.search(text)
    return text[match.start():] if match else text


def extract_totals(text: str) -> dict[str, Decimal | None]:
    block = _totals_block(text)
    result: dict[str, Decimal | None] = {"subtotal": None, "tax": None, "tax_rate": None,
                                         "shipping": Decimal("0.00"), "total": None}
    if (m := SUBTOTAL_RE.search(block)):
        result["subtotal"] = parse_amount(m.group("value"))
    for line in block.splitlines():
        if SUBTOTAL_RE.search(line):
            continue
        if (m := TAX_RE.search(line)) and result["tax"] is None:
            result["tax"] = parse_amount(m.group("value"))
            if m.group("rate"):
                result["tax_rate"] = parse_quantity(m.group("rate"))
    if (m := SHIPPING_RE.search(block)):
        result["shipping"] = parse_amount(m.group("value"))
    totals = [m for m in TOTAL_RE.finditer(block)]
    if totals:
        result["total"] = parse_amount(totals[-1].group("value"))
    return result


# --------------------------------------------------------------------------- public API

def parse_invoice_text(text: str, tables: list | None = None, *, source: str = "<text>",
                       method: str = "text") -> Invoice:
    """Build an :class:`Invoice` from already-extracted text (and optional tables)."""
    invoice = Invoice(source_file=source, extraction_method=method)
    invoice.invoice_number = _first(INVOICE_NUMBER_RE, text)
    issued = next((v for rx in ISSUE_DATE_RES if (v := _first(rx, text))), None)
    invoice.invoice_date = _safe_date(issued, "invoice date", source)
    invoice.due_date = _safe_date(_first(DUE_DATE_RE, text), "due date", source)
    invoice.vendor = extract_vendor(text)
    invoice.currency = detect_currency(text)

    items = items_from_tables(tables or [])
    if items:
        invoice.extraction_method = f"{method}+table"
    else:
        items = items_from_text(text)
    invoice.line_items = items

    totals = extract_totals(text)
    invoice.subtotal = totals["subtotal"]
    invoice.tax = totals["tax"]
    invoice.tax_rate = totals["tax_rate"]
    invoice.shipping = totals["shipping"] or Decimal("0.00")
    invoice.total = totals["total"]
    log.debug("%s: parsed %d line items", source, len(items))
    return invoice


def extract_invoice(path: str | Path, *, ocr_enabled: bool = False, ocr_language: str = "eng") -> Invoice:
    """Extract a single invoice PDF (validation is applied separately)."""
    path = Path(path)
    if not path.is_file():
        raise ExtractionError(f"file not found: {path}")
    doc = read_pdf(path, ocr_enabled=ocr_enabled, ocr_language=ocr_language)
    invoice = parse_invoice_text(doc.text, doc.tables, source=path.name, method=doc.method)
    log.info("extracted %s -> %s (%s, %d items)", path.name, invoice.invoice_number,
             invoice.vendor, len(invoice.line_items))
    return invoice
