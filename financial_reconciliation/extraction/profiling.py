"""Profile columns to auto-suggest data type and key/value role.

Feeds the auto-mapping and the UI's pre-filled field table so the user rarely
has to configure types by hand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any, Dict, List

from ..models.enums import DataType, FieldRole
from ..models.money import parse_decimal
from .grids import is_empty

_MONEY_HINT = re.compile(r"(amount|amt|total|balance|debit|credit|value|price|cost|sum|net|gross|fee|tax)",
                         re.I)
_DATE_HINT = re.compile(r"(date|dt|period|posted|due|as.?of)", re.I)
_ID_HINT = re.compile(r"(id|no|num|number|ref|reference|code|invoice|account|acct|key|sku|isin|cusip)",
                      re.I)


def norm_value(v: Any) -> str:
    """Normalize a cell for cross-column value-overlap comparison."""
    d = parse_decimal(v)
    if d is not None:
        return str(d.normalize())
    return re.sub(r"\s+", " ", str(v).strip().casefold())


@dataclass
class ColumnProfile:
    name: str
    dtype: DataType
    role: FieldRole
    n: int
    non_null: int
    distinct: int
    uniqueness: float
    numeric_frac: float
    date_frac: float
    key_score: float
    sample: List[Any] = dc_field(default_factory=list)
    value_set: frozenset = frozenset()

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "dtype": self.dtype.value, "role": self.role.value,
                "n": self.n, "non_null": self.non_null, "distinct": self.distinct,
                "uniqueness": round(self.uniqueness, 3),
                "numeric_frac": round(self.numeric_frac, 3),
                "key_score": round(self.key_score, 3),
                "sample": [str(s) for s in self.sample[:3]]}


def _looks_date(v: Any) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if not isinstance(v, str):
        return False
    return bool(re.search(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", v)) or \
        bool(re.match(r"\d{1,2}[-/ ][A-Za-z]{3}", v))


def profile_column(name: str, values: List[Any]) -> ColumnProfile:
    non_null = [v for v in values if not is_empty(v)]
    n, k = len(values), len(non_null)
    distinct = len(set(str(v).strip().lower() for v in non_null))
    uniqueness = distinct / k if k else 0.0
    numeric_frac = sum(1 for v in non_null if parse_decimal(v) is not None) / k if k else 0.0
    date_frac = sum(1 for v in non_null if _looks_date(v)) / k if k else 0.0

    if date_frac >= 0.7:
        dtype = DataType.DATE
    elif numeric_frac >= 0.8:
        dtype = DataType.MONEY if _MONEY_HINT.search(name) else DataType.NUMERIC
    elif _DATE_HINT.search(name) and date_frac >= 0.4:
        dtype = DataType.DATE
    else:
        dtype = DataType.TEXT

    # key score: identifier-like name matters most; uniqueness supports it.
    key_score = 0.5 * uniqueness
    if _ID_HINT.search(name):
        key_score += 0.35
    if dtype == DataType.MONEY:
        key_score -= 0.6
    if dtype == DataType.DATE:
        key_score -= 0.2
    key_score = max(0.0, min(1.3, key_score))
    role = FieldRole.KEY if key_score >= 0.6 else FieldRole.VALUE

    value_set = frozenset(norm_value(v) for v in non_null[:2000])
    return ColumnProfile(name=name, dtype=dtype, role=role, n=n, non_null=k,
                         distinct=distinct, uniqueness=uniqueness,
                         numeric_frac=numeric_frac, date_frac=date_frac,
                         key_score=key_score, sample=non_null[:5], value_set=value_set)


def profile_columns(columns: List[str], records: List[Any]) -> List[ColumnProfile]:
    return [profile_column(c, [r.values.get(c) for r in records]) for c in columns]
