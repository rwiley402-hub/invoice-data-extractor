"""Arithmetic and completeness checks for extracted invoices."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import Invoice, ValidationResult

CENT = Decimal("0.01")


def _close(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(a - b) <= tolerance


def validate_invoice(invoice: Invoice, tolerance: Decimal = Decimal("0.01")) -> ValidationResult:
    """Check required fields and that the numbers add up.

    Errors make the invoice invalid; warnings flag things worth a human look
    (e.g. a tax amount that does not match the stated rate).
    """
    result = ValidationResult()

    for field_name in ("invoice_number", "invoice_date", "vendor", "total"):
        if getattr(invoice, field_name) in (None, ""):
            result.errors.append(f"missing {field_name.replace('_', ' ')}")
    if invoice.subtotal is None:
        result.warnings.append("missing subtotal")
    if invoice.tax is None:
        result.warnings.append("missing tax")
    if not invoice.line_items:
        result.errors.append("no line items found")

    for idx, item in enumerate(invoice.line_items, start=1):
        expected = (item.quantity * item.unit_price).quantize(CENT, ROUND_HALF_UP)
        if not _close(expected, item.amount, tolerance):
            result.errors.append(
                f"line {idx} ({item.description}): {item.quantity} x {item.unit_price} = {expected}, "
                f"but amount is {item.amount}"
            )

    items_sum = sum((item.amount for item in invoice.line_items), Decimal("0.00"))
    if invoice.subtotal is not None and invoice.line_items and not _close(items_sum, invoice.subtotal, tolerance):
        result.errors.append(f"line items sum to {items_sum}, but subtotal is {invoice.subtotal}")

    if invoice.subtotal is not None and invoice.tax is not None and invoice.tax_rate is not None:
        expected_tax = (invoice.subtotal * invoice.tax_rate / 100).quantize(CENT, ROUND_HALF_UP)
        if not _close(expected_tax, invoice.tax, tolerance):
            result.warnings.append(
                f"tax {invoice.tax} does not match {invoice.tax_rate}% of subtotal ({expected_tax})"
            )

    if invoice.total is not None:
        base = invoice.subtotal if invoice.subtotal is not None else items_sum
        expected_total = base + (invoice.tax or Decimal("0")) + invoice.shipping
        if not _close(expected_total, invoice.total, tolerance):
            result.errors.append(
                f"subtotal + tax + shipping = {expected_total}, but total is {invoice.total} "
                f"(difference {invoice.total - expected_total})"
            )

    if invoice.due_date and invoice.invoice_date and invoice.due_date < invoice.invoice_date:
        result.warnings.append("due date is before invoice date")

    invoice.validation = result
    return result
