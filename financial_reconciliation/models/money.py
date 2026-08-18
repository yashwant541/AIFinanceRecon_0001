"""Money handling. Monetary and numeric values are Decimal, never float.

Float arithmetic (0.1 + 0.2 != 0.3) manufactures phantom variances in a
reconciliation engine, so all numeric/money parsing funnels through here.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional, Sequence

Money = Decimal

_CURRENCY_STRIP = re.compile(r"[^\d\-.,()%]")


def parse_decimal(
    value: Any,
    *,
    parentheses_negative: bool = True,
    strip_symbols: bool = True,
    null_tokens: Sequence[str] = (),
) -> Optional[Decimal]:
    """Coerce a messy cell into a Decimal, or None if not parseable.

    Handles currency symbols, thousands separators, parenthesised negatives,
    trailing percent, and both '1,234.56' and '1.234,56' conventions.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Decimal(str(value))

    s = str(value).strip()
    if s == "" or s.lower() in null_tokens:
        return None

    negative = False
    if parentheses_negative and s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if strip_symbols:
        for sym in "$€£¥₹¢₩":
            s = s.replace(sym, "")
    s = s.replace(" ", "")
    is_pct = s.endswith("%")
    if is_pct:
        s = s[:-1]
    # Reject anything with letters (e.g. "INV-1001", "12abc") — not a number.
    if re.search(r"[A-Za-z]", s):
        return None

    if "," in s and "." in s:
        # last separator is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.match(r"^-?\d{1,3}(,\d{3})+$", s):
            s = s.replace(",", "")       # thousands grouping
        else:
            s = s.replace(",", ".")      # decimal comma
    s = s.replace(" ", "")

    if s in ("", "-", ".", "-."):
        return None
    try:
        num = Decimal(s)
    except InvalidOperation:
        return None
    if negative:
        num = -num
    if is_pct:
        num = num / Decimal(100)
    return num


def quantize(value: Decimal, places: int = 2, rounding: str = ROUND_HALF_UP) -> Decimal:
    q = Decimal(1).scaleb(-places)
    return value.quantize(q, rounding=rounding)


def to_float(value: Optional[Decimal]) -> Optional[float]:
    """For display/export boundaries only (charts, spreadsheets)."""
    return None if value is None else float(value)
