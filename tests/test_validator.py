from datetime import date
from decimal import Decimal

from invoice_extractor.models import Invoice, LineItem
from invoice_extractor.validator import validate_invoice


def make_invoice(**overrides) -> Invoice:
    base = dict(
        source_file="x.pdf",
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        vendor="Acme Testing Co.",
        currency="USD",
        line_items=[
            LineItem("A", Decimal("2"), Decimal("10.00"), Decimal("20.00")),
            LineItem("B", Decimal("1"), Decimal("5.50"), Decimal("5.50")),
        ],
        subtotal=Decimal("25.50"),
        tax_rate=Decimal("10"),
        tax=Decimal("2.55"),
        shipping=Decimal("4.00"),
        total=Decimal("32.05"),
    )
    base.update(overrides)
    return Invoice(**base)


def test_consistent_invoice_is_valid() -> None:
    result = validate_invoice(make_invoice())
    assert result.is_valid
    assert result.warnings == []


def test_wrong_line_amount_is_an_error() -> None:
    items = [LineItem("A", Decimal("2"), Decimal("10.00"), Decimal("21.00"))]
    invoice = make_invoice(line_items=items, subtotal=Decimal("21.00"), tax=Decimal("2.10"), total=Decimal("27.10"))
    result = validate_invoice(invoice)
    assert not result.is_valid
    assert any("line 1" in e for e in result.errors)


def test_subtotal_mismatch_is_an_error() -> None:
    result = validate_invoice(make_invoice(subtotal=Decimal("30.00"), tax=Decimal("3.00"), total=Decimal("37.00")))
    assert any("sum to" in e for e in result.errors)


def test_total_mismatch_is_an_error() -> None:
    result = validate_invoice(make_invoice(total=Decimal("40.00")))
    assert any("but total is" in e for e in result.errors)


def test_tax_rate_mismatch_is_only_a_warning() -> None:
    result = validate_invoice(make_invoice(tax=Decimal("3.00"), total=Decimal("32.50")))
    assert result.is_valid
    assert any("does not match" in w for w in result.warnings)


def test_tolerance_absorbs_rounding() -> None:
    assert validate_invoice(make_invoice(total=Decimal("32.06")), tolerance=Decimal("0.02")).is_valid


def test_missing_required_fields() -> None:
    result = validate_invoice(make_invoice(invoice_number=None, vendor=None, line_items=[]))
    assert {"missing invoice number", "missing vendor", "no line items found"} <= set(result.errors)


def test_due_before_issue_warns() -> None:
    result = validate_invoice(make_invoice(due_date=date(2025, 12, 1)))
    assert "due date is before invoice date" in result.warnings


def test_validation_is_attached_to_invoice() -> None:
    invoice = make_invoice(total=Decimal("1.00"))
    validate_invoice(invoice)
    assert invoice.to_dict()["validation"]["is_valid"] is False
