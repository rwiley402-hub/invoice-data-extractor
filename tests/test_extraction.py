"""End-to-end extraction tests over the generated sample PDFs.

Ground truth lives in ``samples/expected.json`` (written by scripts/generate_samples.py).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_extractor import ExtractionError, extract_invoice, parse_invoice_text, validate_invoice

SAMPLE_FILES = sorted(p.name for p in (Path(__file__).resolve().parent.parent / "samples").glob("*.pdf"))


def test_there_are_ten_samples() -> None:
    assert len(SAMPLE_FILES) == 10


@pytest.mark.parametrize("filename", SAMPLE_FILES)
def test_header_fields_match_ground_truth(filename: str, samples_dir: Path, expected: dict) -> None:
    truth = expected[filename]
    invoice = extract_invoice(samples_dir / filename)
    assert invoice.invoice_number == truth["invoice_number"]
    assert invoice.invoice_date == date.fromisoformat(truth["invoice_date"])
    assert invoice.due_date == date.fromisoformat(truth["due_date"])
    assert invoice.vendor == truth["vendor"]
    assert invoice.currency == truth["currency"]


@pytest.mark.parametrize("filename", SAMPLE_FILES)
def test_amounts_match_ground_truth(filename: str, samples_dir: Path, expected: dict) -> None:
    truth = expected[filename]
    invoice = extract_invoice(samples_dir / filename)
    assert invoice.subtotal == Decimal(truth["subtotal"])
    assert invoice.tax == Decimal(truth["tax"])
    assert invoice.tax_rate == Decimal(truth["tax_rate"])
    assert invoice.shipping == Decimal(truth["shipping"])
    assert invoice.total == Decimal(truth["total"])


@pytest.mark.parametrize("filename", SAMPLE_FILES)
def test_line_items_match_ground_truth(filename: str, samples_dir: Path, expected: dict) -> None:
    truth = expected[filename]["line_items"]
    items = extract_invoice(samples_dir / filename).line_items
    assert len(items) == len(truth)
    for got, want in zip(items, truth, strict=True):
        assert got.description == want["description"]
        assert got.quantity == Decimal(want["quantity"])
        assert got.unit_price == Decimal(want["unit_price"])
        assert got.amount == Decimal(want["amount"])


@pytest.mark.parametrize("filename", SAMPLE_FILES)
def test_validation_matches_expectation(filename: str, samples_dir: Path, expected: dict) -> None:
    result = validate_invoice(extract_invoice(samples_dir / filename))
    assert result.is_valid is expected[filename]["expected_valid"], result.errors


def test_grid_layout_uses_detected_table(samples_dir: Path) -> None:
    assert extract_invoice(samples_dir / "invoice_01_northwind.pdf").extraction_method == "text+table"
    assert extract_invoice(samples_dir / "invoice_03_bluepeak.pdf").extraction_method == "text"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError):
        extract_invoice(tmp_path / "nope.pdf")


def test_pdf_without_text_layer_requires_ocr(tmp_path: Path) -> None:
    from reportlab.pdfgen import canvas

    scan = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(scan))
    c.rect(100, 100, 200, 200, fill=1)  # graphics only, no text layer - like a scanned page
    c.showPage()
    c.save()
    with pytest.raises(ExtractionError, match="no text layer"):
        extract_invoice(scan)


def test_parse_plain_text_with_qty_first_columns() -> None:
    text = "\n".join([
        "INVOICE Invoice No. XY-0042",
        "Date: 02 Feb 2026",
        "From: Example Widgets Ltd To:",
        "Qty Description Rate Line Total",
        "2 Widget, large £10.00 £20.00",
        "3 Widget, small £2.50 £7.50",
        "Subtotal £27.50",
        "VAT (20%) £5.50",
        "Amount Due £33.00",
    ])
    invoice = parse_invoice_text(text)
    assert invoice.vendor == "Example Widgets Ltd"
    assert invoice.invoice_number == "XY-0042"
    assert invoice.invoice_date == date(2026, 2, 2)
    assert [i.description for i in invoice.line_items] == ["Widget, large", "Widget, small"]
    assert invoice.currency == "GBP"
    assert invoice.total == Decimal("33.00")
    assert validate_invoice(invoice).is_valid
