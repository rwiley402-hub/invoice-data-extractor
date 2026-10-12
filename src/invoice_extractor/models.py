"""Domain models for extracted invoices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "amount": float(self.amount),
        }


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {"is_valid": self.is_valid, "errors": self.errors, "warnings": self.warnings}


@dataclass
class Invoice:
    source_file: str
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    vendor: str | None = None
    currency: str | None = None
    line_items: list[LineItem] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax_rate: Decimal | None = None
    tax: Decimal | None = None
    shipping: Decimal = Decimal("0.00")
    total: Decimal | None = None
    extraction_method: str = "text"
    validation: ValidationResult = field(default_factory=ValidationResult)

    def to_dict(self) -> dict[str, Any]:
        def num(value: Decimal | None) -> float | None:
            return None if value is None else float(value)

        return {
            "source_file": self.source_file,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "vendor": self.vendor,
            "currency": self.currency,
            "line_items": [item.to_dict() for item in self.line_items],
            "subtotal": num(self.subtotal),
            "tax_rate": num(self.tax_rate),
            "tax": num(self.tax),
            "shipping": num(self.shipping),
            "total": num(self.total),
            "extraction_method": self.extraction_method,
            "validation": self.validation.to_dict(),
        }
