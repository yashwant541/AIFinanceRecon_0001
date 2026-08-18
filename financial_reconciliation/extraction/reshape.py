"""Reshape wide financial tables into long / tidy form.

The processed reference documents use a tidy schema — one row per data point:

    [dimension columns ..., Value]

e.g. a wide "Statement of results" (Line item | Q1'26 | Q1'25 | Change) becomes

    Line item          | Period | Value
    Operating income   | Q1'26  | 5902
    Operating income   | Q1'25  | 5379
    ...

Melting both sides into this shape lets reconciliation compare every cell by its
(label, period) key, which is exactly how the reference files are structured.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .grids import is_number


def detect_id_value_cols(columns: List[str], rows: List[Dict[str, Any]]
                         ) -> Tuple[List[str], List[str]]:
    """Leading label columns become ids; the rest are values to unpivot."""
    id_cols: List[str] = []
    for c in columns:
        vals = [r.get(c) for r in rows]
        nonnull = [v for v in vals if v not in (None, "")]
        num_frac = (sum(1 for v in nonnull if is_number(v)) / len(nonnull)
                    if nonnull else 0.0)
        if num_frac < 0.5:
            id_cols.append(c)
        else:
            break
    if not id_cols:
        id_cols = [columns[0]]
    value_cols = [c for c in columns if c not in id_cols]
    return id_cols, value_cols


def melt(columns: List[str], rows: List[Dict[str, Any]],
         period_name: str = "Period", value_name: str = "Value",
         drop_blank: bool = True) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Return (long_columns, long_rows)."""
    id_cols, value_cols = detect_id_value_cols(columns, rows)
    long_rows: List[Dict[str, Any]] = []
    for r in rows:
        label = {c: r.get(c) for c in id_cols}
        if all(v in (None, "") for v in label.values()):
            continue
        for vc in value_cols:
            val = r.get(vc)
            if drop_blank and (val is None or val == ""):
                continue
            row = dict(label)
            row[period_name] = vc
            row[value_name] = val
            long_rows.append(row)
    return id_cols + [period_name, value_name], long_rows


def melt_table(table, period_name: str = "Period", value_name: str = "Value"):
    """Melt a FinancialTable's rows; returns (columns, rows)."""
    rows = [r.values for r in table.records]
    return melt(table.columns, rows, period_name, value_name)
