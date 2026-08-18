"""Export a ReconciliationResult to a multi-sheet XLSX workbook (bytes).

Text pulled out of PDFs and Word files regularly contains control characters
(\\x00-\\x08, \\x0b, \\x0c, \\x0e-\\x1f). openpyxl refuses to write those and
raises IllegalCharacterError, so every string is sanitised on the way out.
"""
from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from ..models.results import ReconciliationResult
from .serialize import _match_row, _unmatched_row, _val

# control characters Excel/openpyxl will not accept in a cell
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MAX_CELL = 32767  # Excel's hard limit on characters in one cell


def clean_cell(value: Any) -> Any:
    """Make any value safe for an Excel cell."""
    if isinstance(value, str):
        out = _ILLEGAL.sub("", value)
        return out[:_MAX_CELL] if len(out) > _MAX_CELL else out
    if isinstance(value, float):
        # inf/-inf/nan cannot be written; surface them as text
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
    return value


def _frame(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame({"(empty)": []})
    df = pd.DataFrame([{clean_cell(k): clean_cell(v) for k, v in r.items()} for r in rows])
    return df


class WorkbookExporter:
    def export(self, result: ReconciliationResult) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            _frame([result.summary]).to_excel(xw, sheet_name="summary", index=False)
            _frame([{
                "field": f.field, "dtype": f.dtype,
                "sum_left_minus_right": _val(f.sum_left_minus_right),
                "sum_abs_difference": _val(f.sum_abs_difference),
                "n_breaks": f.n_breaks} for f in result.field_variance]
            ).to_excel(xw, sheet_name="field_variance", index=False)
            _sheet(xw, "breaks", [_match_row(m) for m in result.breaks])
            _sheet(xw, "reconciled", [_match_row(m) for m in result.reconciled])
            _sheet(xw, "unmatched_left", [_unmatched_row(u) for u in result.unmatched_left])
            _sheet(xw, "unmatched_right", [_unmatched_row(u) for u in result.unmatched_right])
        buf.seek(0)
        return buf.getvalue()


def _sheet(xw, name: str, rows) -> None:
    _frame(rows).to_excel(xw, sheet_name=name, index=False)
