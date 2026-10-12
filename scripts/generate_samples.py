"""Generate deterministic sample invoice PDFs for the extractor demo.

All vendors, customers and products are fictional. A fixed random seed and
reportlab's ``invariant`` mode make the output byte-for-byte reproducible.

Three visual layouts are produced so the extractor has to cope with variety:

* ``grid``    - classic bordered table (pdfplumber can detect the table lines)
* ``modern``  - borderless columns under a coloured header band
* ``compact`` - quantity-first columns, "From:" vendor label, GBP

Alongside the PDFs a ``samples/expected.json`` ground-truth manifest is written;
the test-suite compares extracted values against it.

Usage::

    python scripts/generate_samples.py [--out samples]
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

SEED = 20260412
CENT = Decimal("0.01")
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "samples"


@dataclass(frozen=True)
class Vendor:
    key: str
    name: str
    address: tuple[str, ...]
    currency: str
    symbol: str
    symbol_suffix: bool
    number_style: str  # "us" -> 1,234.56 | "eu" -> 1.234,56
    layout: str
    date_fmt: str
    number_label: str
    number_pattern: str
    tax_label: str
    tax_rate: Decimal
    total_label: str
    catalog: tuple[tuple[str, str], ...]
    shipping: bool = False
    page_size: tuple[float, float] = LETTER


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(CENT, ROUND_HALF_UP)


@dataclass
class InvoiceSpec:
    vendor: Vendor
    number: str
    issued: date
    due: date
    customer: tuple[str, ...]
    items: list[LineItem]
    shipping: Decimal = Decimal("0.00")
    total_error: Decimal = Decimal("0.00")  # deliberate mistake for validation demo
    filename: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((i.amount for i in self.items), Decimal("0.00"))

    @property
    def tax(self) -> Decimal:
        return (self.subtotal * self.vendor.tax_rate / 100).quantize(CENT, ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax + self.shipping + self.total_error


VENDORS: tuple[Vendor, ...] = (
    Vendor(
        key="northwind",
        name="Northwind Office Supplies",
        address=("1820 Larkspur Avenue, Suite 400", "Portland, OR 97209", "billing@northwind-office.example"),
        currency="USD", symbol="$", symbol_suffix=False, number_style="us",
        layout="grid", date_fmt="%Y-%m-%d",
        number_label="Invoice Number:", number_pattern="NW-2026-{n:04d}",
        tax_label="Sales Tax", tax_rate=Decimal("8.25"), total_label="Total",
        catalog=(
            ("Recycled copy paper A4 (box of 5 reams)", "24.50"),
            ("Ergonomic mesh office chair", "189.00"),
            ("Gel ink pens, blue (pack of 12)", "8.75"),
            ("Whiteboard markers assorted (set of 8)", "11.20"),
            ("Heavy-duty stapler", "32.40"),
            ("Monitor arm, dual mount", "74.95"),
            ("Desk organiser, bamboo", "19.99"),
        ),
        shipping=True,
    ),
    Vendor(
        key="bluepeak",
        name="Bluepeak Cloud Services",
        address=("77 Harbor Point Drive", "Austin, TX 78701", "accounts@bluepeak.example"),
        currency="USD", symbol="$", symbol_suffix=False, number_style="us",
        layout="modern", date_fmt="%B %d, %Y",
        number_label="Invoice #", number_pattern="BPC-{n:05d}",
        tax_label="Tax", tax_rate=Decimal("6.25"), total_label="Amount Due",
        catalog=(
            ("Compute instances (vCPU-hours)", "0.45"),
            ("Block storage (GB-month)", "0.10"),
            ("Managed PostgreSQL, standard tier", "149.00"),
            ("Load balancer (hours)", "0.03"),
            ("Premium support plan", "299.00"),
            ("Object storage egress (GB)", "0.08"),
        ),
    ),
    Vendor(
        key="alderfinch",
        name="Alder & Finch Design Studio",
        address=("14 Weaver's Yard", "Bristol BS1 4QA, United Kingdom", "studio@alderfinch.example"),
        currency="GBP", symbol="£", symbol_suffix=False, number_style="us",
        layout="compact", date_fmt="%d %b %Y",
        number_label="Invoice No.", number_pattern="AF/{n:04d}",
        tax_label="VAT", tax_rate=Decimal("20"), total_label="Amount Due",
        catalog=(
            ("Brand identity workshop", "450.00"),
            ("Logo concept round", "680.00"),
            ("Illustration (per piece)", "220.00"),
            ("Website UI design (per day)", "520.00"),
            ("Print-ready artwork prep", "95.00"),
        ),
        page_size=A4,
    ),
    Vendor(
        key="kestrel",
        name="Kestrel Logistik GmbH",
        address=("Hafenstrasse 112", "20457 Hamburg, Germany", "VAT ID: DE 298 114 553"),
        currency="EUR", symbol="€", symbol_suffix=True, number_style="eu",
        layout="grid", date_fmt="%d.%m.%Y",
        number_label="Invoice #:", number_pattern="KL-{n:05d}",
        tax_label="VAT", tax_rate=Decimal("19"), total_label="Total Due",
        catalog=(
            ("Pallet storage (per pallet-week)", "6.80"),
            ("Pick and pack service (per order)", "2.35"),
            ("Road freight Hamburg to Munich", "640.00"),
            ("Customs documentation fee", "45.00"),
            ("Shrink wrapping (per pallet)", "4.50"),
        ),
        page_size=A4,
    ),
    Vendor(
        key="copperleaf",
        name="Copperleaf Catering Co.",
        address=("305 Mill Street", "Burlington, VT 05401", "events@copperleaf.example"),
        currency="USD", symbol="$", symbol_suffix=False, number_style="us",
        layout="modern", date_fmt="%B %d, %Y",
        number_label="Invoice #", number_pattern="CC-{n:04d}",
        tax_label="Meals Tax", tax_rate=Decimal("9"), total_label="Total Due",
        catalog=(
            ("Breakfast buffet (per guest)", "18.50"),
            ("Boxed lunch, vegetarian", "14.25"),
            ("Boxed lunch, classic", "15.75"),
            ("Coffee and tea service (per guest)", "4.80"),
            ("Afternoon pastry platter", "65.00"),
            ("Event staff (per hour)", "38.00"),
        ),
    ),
)

CUSTOMERS: tuple[tuple[str, ...], ...] = (
    ("Harborview Analytics LLC", "Attn: Accounts Payable", "500 Pine Street", "Seattle, WA 98101"),
    ("Meridian Health Partners", "Finance Department", "42 Commerce Plaza", "Denver, CO 80202"),
    ("Quillstone Publishing Ltd", "Attn: Priya Raman", "8 Cathedral Walk", "Exeter EX1 1HB"),
    ("Tidewater Robotics Inc.", "Procurement", "1100 Innovation Way", "Raleigh, NC 27606"),
    ("Silverbirch Ventures", "Attn: Marco Lindqvist", "Kungsgatan 21", "111 56 Stockholm"),
)


# --------------------------------------------------------------------------- formatting

def fmt_number(value: Decimal, style: str) -> str:
    text = f"{value:,.2f}"
    if style == "eu":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def fmt_money(value: Decimal, vendor: Vendor) -> str:
    number = fmt_number(value, vendor.number_style)
    return f"{number} {vendor.symbol}" if vendor.symbol_suffix else f"{vendor.symbol}{number}"


def fmt_qty(value: Decimal) -> str:
    return f"{value:g}" if value != value.to_integral() else str(int(value))


# --------------------------------------------------------------------------- layouts

def _draw_lines(c: canvas.Canvas, x: float, y: float, lines: tuple[str, ...] | list[str],
                font: str = "Helvetica", size: float = 9, leading: float = 12) -> float:
    c.setFont(font, size)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def _totals_block(c: canvas.Canvas, inv: InvoiceSpec, x_label: float, x_value: float, y: float) -> float:
    v = inv.vendor
    rows: list[tuple[str, Decimal]] = [("Subtotal", inv.subtotal)]
    rows.append((f"{v.tax_label} ({fmt_qty(v.tax_rate)}%)", inv.tax))
    if inv.shipping:
        rows.append(("Shipping", inv.shipping))
    rows.append((v.total_label, inv.total))
    for i, (label, value) in enumerate(rows):
        bold = i == len(rows) - 1
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(x_label, y, label)
        c.drawRightString(x_value, y, fmt_money(value, v))
        y -= 16
    return y


def layout_grid(c: canvas.Canvas, inv: InvoiceSpec) -> None:
    v = inv.vendor
    width, height = v.page_size
    left, right = 50, width - 50
    c.setFont("Helvetica-Bold", 20)
    c.drawString(left, height - 60, v.name)
    _draw_lines(c, left, height - 80, v.address)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawRightString(right, height - 115, "INVOICE")
    c.setFillColor(colors.black)

    y = height - 150
    _draw_lines(c, left, y, ["Bill To:", *inv.customer], size=10, leading=13)
    meta = [
        f"{v.number_label} {inv.number}",
        f"Invoice Date: {inv.issued.strftime(v.date_fmt)}",
        f"Due Date: {inv.due.strftime(v.date_fmt)}",
    ]
    c.setFont("Helvetica", 10)
    for i, line in enumerate(meta):
        c.drawRightString(right, y - i * 13, line)

    data = [["Description", "Qty", "Unit Price", "Amount"]]
    for item in inv.items:
        data.append([item.description, fmt_qty(item.quantity),
                     fmt_money(item.unit_price, v), fmt_money(item.amount, v)])
    table_width = right - left
    table = Table(data, colWidths=[table_width * 0.52, table_width * 0.1, table_width * 0.19, table_width * 0.19])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#444444")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE3EA")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    _, th = table.wrapOn(c, table_width, height)
    table_top = y - 13 * (len(inv.customer) + 1) - 25
    table.drawOn(c, left, table_top - th)

    _totals_block(c, inv, right - 200, right, table_top - th - 30)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(left, 60, "Payment terms: Net 30. Please reference the invoice number with your payment.")


def layout_modern(c: canvas.Canvas, inv: InvoiceSpec) -> None:
    v = inv.vendor
    width, height = v.page_size
    left, right = 48, width - 48
    accent = colors.HexColor("#1F6F8B") if v.key == "bluepeak" else colors.HexColor("#9C4A1A")
    c.setFillColor(accent)
    c.rect(0, height - 110, width, 110, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(left, height - 55, v.name)
    c.setFont("Helvetica", 9)
    c.drawString(left, height - 75, "  |  ".join(v.address))
    c.setFillColor(colors.black)

    y = height - 150
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "BILLED TO")
    _draw_lines(c, left, y - 15, inv.customer, size=10, leading=13)
    meta = [
        ("Invoice #", inv.number),
        ("Issue Date:", inv.issued.strftime(v.date_fmt)),
        ("Due Date:", inv.due.strftime(v.date_fmt)),
    ]
    for i, (label, value) in enumerate(meta):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(right - 210, y - i * 15, label)
        c.setFont("Helvetica", 10)
        c.drawRightString(right, y - i * 15, value)

    y -= 15 + 13 * len(inv.customer) + 30
    cols = (left + 6, right - 220, right - 110, right - 6)  # desc, qty(right), rate(right), amount(right)
    c.setFillColor(colors.HexColor("#F1F1F1"))
    c.rect(left, y - 6, right - left, 20, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(cols[0], y, "ITEM DESCRIPTION")
    c.drawRightString(cols[1], y, "QTY")
    c.drawRightString(cols[2], y, "RATE")
    c.drawRightString(cols[3], y, "AMOUNT")
    y -= 22
    c.setFont("Helvetica", 9.5)
    for item in inv.items:
        c.drawString(cols[0], y, item.description)
        c.drawRightString(cols[1], y, fmt_qty(item.quantity))
        c.drawRightString(cols[2], y, fmt_money(item.unit_price, v))
        c.drawRightString(cols[3], y, fmt_money(item.amount, v))
        y -= 18
    c.setStrokeColor(accent)
    c.line(left, y + 6, right, y + 6)
    _totals_block(c, inv, right - 210, right - 6, y - 16)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(left, 55, "Thank you for your business! Questions? Reply to the address above.")


def layout_compact(c: canvas.Canvas, inv: InvoiceSpec) -> None:
    v = inv.vendor
    width, height = v.page_size
    left, right = 56, width - 56
    c.setFont("Helvetica-Bold", 26)
    c.drawString(left, height - 70, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(right, height - 58, f"{v.number_label} {inv.number}")
    c.drawRightString(right, height - 72, f"Date: {inv.issued.strftime(v.date_fmt)}")
    c.drawRightString(right, height - 86, f"Payment due: {inv.due.strftime(v.date_fmt)}")

    y = height - 130
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, f"From: {v.name}")
    _draw_lines(c, left, y - 14, v.address, size=9)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left + 270, y, "To:")
    _draw_lines(c, left + 270, y - 14, inv.customer, size=9)

    y -= 14 + 12 * max(len(v.address), len(inv.customer)) + 30
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(left, y, "Qty")
    c.drawString(left + 40, y, "Description")
    c.drawRightString(right - 90, y, "Rate")
    c.drawRightString(right, y, "Line Total")
    c.line(left, y - 5, right, y - 5)
    y -= 20
    c.setFont("Helvetica", 9.5)
    for item in inv.items:
        c.drawString(left, y, fmt_qty(item.quantity))
        c.drawString(left + 40, y, item.description)
        c.drawRightString(right - 90, y, fmt_money(item.unit_price, v))
        c.drawRightString(right, y, fmt_money(item.amount, v))
        y -= 16
    c.line(left, y + 8, right, y + 8)
    _totals_block(c, inv, right - 190, right, y - 14)
    c.setFont("Helvetica", 8)
    c.drawString(left, 50, "Bank transfer: Alder & Finch Ltd, sort code 00-00-00 (example only). Company no. 00000000.")


LAYOUTS: dict[str, Callable[[canvas.Canvas, InvoiceSpec], None]] = {
    "grid": layout_grid,
    "modern": layout_modern,
    "compact": layout_compact,
}


# --------------------------------------------------------------------------- generation

def build_specs(rng: random.Random) -> list[InvoiceSpec]:
    specs: list[InvoiceSpec] = []
    for vendor in VENDORS:
        for _ in range(2):
            n_items = rng.randint(3, min(6, len(vendor.catalog)))
            picks = rng.sample(vendor.catalog, n_items)
            items = []
            for desc, price in picks:
                unit = Decimal(price)
                if unit < 1:
                    qty = Decimal(rng.randrange(100, 2400, 10))
                elif "hour" in desc and vendor.key == "copperleaf":
                    qty = Decimal(rng.choice(["4", "6", "7.5", "8"]))
                else:
                    qty = Decimal(rng.randint(1, 40 if unit < 50 else 4))
                items.append(LineItem(desc, qty, unit))
            issued = date(2026, 1, 5) + timedelta(days=rng.randint(0, 240))
            due = issued + timedelta(days=rng.choice([14, 30, 30, 45]))
            shipping = Decimal(rng.choice(["12.50", "18.00", "24.95"])) if vendor.shipping else Decimal("0.00")
            number = vendor.number_pattern.format(n=rng.randint(10, 9999))
            specs.append(InvoiceSpec(
                vendor=vendor, number=number, issued=issued, due=due,
                customer=rng.choice(CUSTOMERS), items=items, shipping=shipping,
            ))
    # One deliberately inconsistent invoice so the validator has something to catch.
    specs[-1].total_error = Decimal("10.00")
    specs[-1].notes.append("Printed total is 10.00 higher than subtotal + tax (intentional).")
    for i, spec in enumerate(specs, start=1):
        spec.filename = f"invoice_{i:02d}_{spec.vendor.key}.pdf"
    return specs


def render(spec: InvoiceSpec, out_dir: Path) -> Path:
    path = out_dir / spec.filename
    c = canvas.Canvas(str(path), pagesize=spec.vendor.page_size, invariant=1)
    c.setTitle(f"Invoice {spec.number}")
    c.setAuthor(spec.vendor.name)
    LAYOUTS[spec.vendor.layout](c, spec)
    c.showPage()
    c.save()
    return path


def manifest_entry(spec: InvoiceSpec) -> dict:
    return {
        "file": spec.filename,
        "layout": spec.vendor.layout,
        "invoice_number": spec.number,
        "invoice_date": spec.issued.isoformat(),
        "due_date": spec.due.isoformat(),
        "vendor": spec.vendor.name,
        "currency": spec.vendor.currency,
        "line_items": [
            {"description": i.description, "quantity": str(i.quantity),
             "unit_price": str(i.unit_price), "amount": str(i.amount)}
            for i in spec.items
        ],
        "subtotal": str(spec.subtotal),
        "tax_rate": str(spec.vendor.tax_rate),
        "tax": str(spec.tax),
        "shipping": str(spec.shipping),
        "total": str(spec.total),
        "expected_valid": spec.total_error == 0,
        "notes": spec.notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: samples/)")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    specs = build_specs(random.Random(args.seed))
    for spec in specs:
        print(f"wrote {render(spec, args.out)}")
    manifest = args.out / "expected.json"
    manifest.write_text(json.dumps([manifest_entry(s) for s in specs], indent=2) + "\n", encoding="utf-8")
    print(f"wrote {manifest}")


if __name__ == "__main__":
    main()
