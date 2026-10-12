from datetime import date
from decimal import Decimal

import pytest

from invoice_extractor.parsing import ParseError, detect_currency, parse_amount, parse_date, parse_quantity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,234.56", Decimal("1234.56")),
        ("1.234,56 €", Decimal("1234.56")),
        ("£220.00", Decimal("220.00")),
        ("0,45 €", Decimal("0.45")),
        ("2560.00", Decimal("2560.00")),
        ("-$10.00", Decimal("-10.00")),
        ("($10.00)", Decimal("-10.00")),
    ],
)
def test_parse_amount(raw: str, expected: Decimal) -> None:
    assert parse_amount(raw) == expected


def test_parse_amount_rejects_garbage() -> None:
    with pytest.raises(ParseError):
        parse_amount("$")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-14", date(2026, 3, 14)),
        ("14.03.2026", date(2026, 3, 14)),
        ("March 14, 2026", date(2026, 3, 14)),
        ("Mar. 14, 2026", date(2026, 3, 14)),
        ("14 Mar 2026", date(2026, 3, 14)),
        ("03/14/2026", date(2026, 3, 14)),
    ],
)
def test_parse_date(raw: str, expected: date) -> None:
    assert parse_date(raw) == expected


def test_parse_date_rejects_unknown_format() -> None:
    with pytest.raises(ParseError):
        parse_date("the fourteenth of March")


def test_parse_quantity_accepts_decimal_comma() -> None:
    assert parse_quantity("7,5") == Decimal("7.5")


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Total $10.00 $5.00", "USD"),
        ("Summe 10,00 €", "EUR"),
        ("Due £5.00", "GBP"),
        ("Amount in CHF 10.00", "CHF"),
        ("no money here", None),
    ],
)
def test_detect_currency(text: str, code: str | None) -> None:
    assert detect_currency(text) == code
