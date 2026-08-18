"""A Grid is a rectangular list-of-rows of raw cell values (str / number / None).

All table detectors operate on Grids so the same header-detection and
region-detection logic works identically for Excel, CSV, PDF and DOCX.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from ..models.money import parse_decimal

Row = List[Any]
Grid = List[Row]


def is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return parse_decimal(v) is not None if isinstance(v, str) else False


def is_date(v: Any) -> bool:
    return isinstance(v, (date, datetime))


def is_texty(v: Any) -> bool:
    """Non-empty, not obviously a number/date — i.e. a plausible label."""
    return not is_empty(v) and not is_number(v) and not is_date(v)


def cell_str(v: Any) -> str:
    if is_empty(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def normalize_grid(grid: Grid) -> Grid:
    """Pad ragged rows to equal width; leave values untouched."""
    width = max((len(r) for r in grid), default=0)
    return [list(r) + [None] * (width - len(r)) for r in grid]


def row_is_empty(row: Row) -> bool:
    return all(is_empty(c) for c in row)


def col_is_empty(grid: Grid, j: int) -> bool:
    return all(is_empty(r[j]) for r in grid if j < len(r))


def trim(grid: Grid) -> Grid:
    """Drop fully-empty edge rows and columns."""
    g = [r for r in grid if not row_is_empty(r)]
    if not g:
        return []
    g = normalize_grid(g)
    width = len(g[0])
    keep = [j for j in range(width) if not col_is_empty(g, j)]
    return [[r[j] for j in keep] for r in g]
