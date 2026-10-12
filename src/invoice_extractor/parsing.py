"""Low-level parsing helpers for money, quantities, dates and currencies."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS: dict[str, str] = {"$": "USD", "€": "EUR", "£": "GBP"}
_SYMBOL_CLASS = "[$€£]"

# A money value: optional leading symbol, digits with thousands separators and two
# decimals in either US (1,234.56) or European (1.234,56) style, optional trailing symbol.
MONEY_PATTERN = (
    rf"(?:{_SYMBOL_CLASS}\s?)?-?(?:\d{{1,3}}(?:[.,]\d{{3}})+|\d+)[.,]\d{{2}}(?:\s?{_SYMBOL_CLASS})?"
)
MONEY_RE = re.compile(MONEY_PATTERN)

DATE_PATTERN = (
    r"\d{4}-\d{2}-\d{2}"                      # 2026-03-14
    r"|\d{1,2}\.\d{1,2}\.\d{4}"               # 14.03.2026
    r"|\d{1,2}/\d{1,2}/\d{4}"                 # 03/14/2026 (US, month first)
    r"|[A-Z][a-z]+\.? \d{1,2},? \d{4}"        # March 14, 2026 / Mar 14 2026
    r"|\d{1,2} [A-Z][a-z]+\.? \d{4}"          # 14 Mar 2026 / 14 March 2026
)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%d %b %Y",
    "%d %B %Y",
)


class ParseError(ValueError):
    """Raised when a token cannot be interpreted."""


def parse_amount(raw: str) -> Decimal:
    """Parse a money string such as ``$1,234.56`` or ``1.234,56 €`` into a Decimal."""
    text = re.sub(rf"{_SYMBOL_CLASS}|\s|[A-Z]{{3}}", "", raw.strip())
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("-()")
    if not text:
        raise ParseError(f"empty amount: {raw!r}")
    last_dot, last_comma = text.rfind("."), text.rfind(",")
    if last_comma > last_dot:
        # European style: '.' groups thousands, ',' is the decimal mark.
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"invalid amount: {raw!r}") from exc
    return -value if negative else value


def parse_quantity(raw: str) -> Decimal:
    text = raw.strip().replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"invalid quantity: {raw!r}") from exc


def parse_date(raw: str) -> date:
    text = re.sub(r"\s+", " ", raw.strip()).replace(".,", ",")
    # "Mar. 14, 2026" -> "Mar 14, 2026" (only strips dots that follow a letter)
    candidates = (text, re.sub(r"([A-Za-z])\.", r"\1", text))
    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    raise ParseError(f"unrecognised date: {raw!r}")


def detect_currency(text: str) -> str | None:
    """Return the ISO code of the most frequent currency symbol/code in ``text``."""
    counts: dict[str, int] = {}
    for symbol, code in CURRENCY_SYMBOLS.items():
        counts[code] = counts.get(code, 0) + text.count(symbol)
    for code in ("USD", "EUR", "GBP", "CAD", "AUD", "CHF"):
        counts[code] = counts.get(code, 0) + len(re.findall(rf"\b{code}\b", text))
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] else None
