"""Serialize domain results to JSON-friendly dicts for the web layer."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from ..models.money import to_float
from ..models.results import (Match, ReconciliationResult, StrategyScore,
                              UnmatchedRecord)


def _val(v: Any) -> Any:
    if isinstance(v, Decimal):
        return to_float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _match_row(m: Match) -> Dict[str, Any]:
    row: Dict[str, Any] = {k: _val(v) for k, v in m.key_values.items()}
    row["match_type"] = m.match_type.value
    row["confidence"] = round(m.confidence * 100, 1)
    for c in m.field_comparisons:
        row[f"{c.field}__left"] = _val(c.left_value)
        row[f"{c.field}__right"] = _val(c.right_value)
        row[f"{c.field}__diff"] = _val(c.difference)
        row[f"{c.field}__ok"] = c.within_tolerance
    row["break_fields"] = ", ".join(m.break_fields)
    row["explanation"] = m.explanation
    row["left_files"] = m.left_source_files
    row["right_files"] = m.right_source_files
    return row


def _unmatched_row(u: UnmatchedRecord) -> Dict[str, Any]:
    row = {k: _val(v) for k, v in u.values.items()}
    row["source_files"] = u.source_files
    return row


def result_to_dict(result: ReconciliationResult, cap: int = 250) -> Dict[str, Any]:
    fv = [{"field": f.field, "dtype": f.dtype,
           "sum_left_minus_right": _val(f.sum_left_minus_right),
           "sum_abs_difference": _val(f.sum_abs_difference),
           "n_breaks": f.n_breaks} for f in result.field_variance]
    return {
        "summary": result.summary,
        "field_variance": fv,
        "reconciled": [_match_row(m) for m in result.reconciled[:cap]],
        "breaks": [_match_row(m) for m in result.breaks[:cap]],
        "unmatched_left": [_unmatched_row(u) for u in result.unmatched_left[:cap]],
        "unmatched_right": [_unmatched_row(u) for u in result.unmatched_right[:cap]],
        "truncated": {
            "reconciled": len(result.reconciled) > cap,
            "breaks": len(result.breaks) > cap,
            "unmatched_left": len(result.unmatched_left) > cap,
            "unmatched_right": len(result.unmatched_right) > cap,
        },
    }
