"""Compute per-field variance for matched pairs and categorize outcomes."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..config.settings import EngineConfig, FieldConfig
from ..models.enums import DataType, MatchType, RecordStatus
from ..models.money import quantize
from ..models.results import (CanonicalRecord, FieldComparison, FieldVariance, Match,
                              ReconciliationResult, UnmatchedRecord)
from ..matching.matcher import MatchLink
from ..matching.similarity import string_similarity


class Reconciler:
    def __init__(self, config: EngineConfig) -> None:
        self._cfg = config
        self._key_fields = config.key_fields()
        self._value_fields = config.value_fields()

    def reconcile(self, links: List[MatchLink],
                  unmatched_left: List[CanonicalRecord],
                  unmatched_right: List[CanonicalRecord],
                  n_left: int, n_right: int, fuzzy_backend: str) -> ReconciliationResult:
        reconciled: List[Match] = []
        breaks: List[Match] = []
        variance_acc: Dict[str, Dict[str, Any]] = {
            f.name: {"sum": Decimal(0), "abs": Decimal(0), "breaks": 0, "dtype": f.dtype.value}
            for f in self._value_fields}

        for link in links:
            comparisons, broke = self._compare(link)
            key_values = {k.name: link.left.values.get(k.name) for k in self._key_fields}
            for c in comparisons:
                if c.difference is not None and isinstance(c.difference, Decimal):
                    variance_acc[c.field]["sum"] += c.difference
                    variance_acc[c.field]["abs"] += abs(c.difference)
                if not c.within_tolerance:
                    variance_acc[c.field]["breaks"] += 1
            status = RecordStatus.RECONCILED if not broke else RecordStatus.BREAK
            match = Match(
                left_key=link.left.key, right_key=link.right.key,
                match_type=link.match_type, confidence=link.confidence,
                strategy_scores=link.strategy_scores, explanation=link.explanation,
                field_comparisons=comparisons, status=status, break_fields=broke,
                key_values=key_values,
                left_source_files=link.left.source_files,
                right_source_files=link.right.source_files)
            (breaks if broke else reconciled).append(match)

        field_variance = [
            FieldVariance(field=name,
                          dtype=acc["dtype"],
                          sum_left_minus_right=quantize(acc["sum"], self._cfg.normalization.decimal_places)
                              if acc["dtype"] in ("money", "numeric") else None,
                          sum_abs_difference=quantize(acc["abs"], self._cfg.normalization.decimal_places)
                              if acc["dtype"] in ("money", "numeric") else None,
                          n_breaks=acc["breaks"])
            for name, acc in variance_acc.items()]

        un_left = [self._unmatched(r, "left") for r in unmatched_left]
        un_right = [self._unmatched(r, "right") for r in unmatched_right]

        n_pairs = len(links)
        n_exact = sum(1 for l in links if l.match_type == MatchType.EXACT)
        summary = {
            "fuzzy_backend": fuzzy_backend,
            "left_records": n_left,
            "right_records": n_right,
            "matched_pairs": n_pairs,
            "matched_exact": n_exact,
            "matched_fuzzy_or_semantic": n_pairs - n_exact,
            "reconciled": len(reconciled),
            "breaks": len(breaks),
            "unmatched_left": len(un_left),
            "unmatched_right": len(un_right),
            "reconciliation_rate": round(100.0 * len(reconciled) / (n_pairs or 1), 2),
            "match_rate_left": round(100.0 * n_pairs / (n_left or 1), 2),
            "match_rate_right": round(100.0 * n_pairs / (n_right or 1), 2),
        }
        return ReconciliationResult(reconciled, breaks, un_left, un_right,
                                    field_variance, summary)

    # -- comparison ---------------------------------------------------------
    def _compare(self, link: MatchLink):
        comparisons: List[FieldComparison] = []
        broke: List[str] = []
        for f in self._value_fields:
            comp = self._compare_field(f, link.left.values.get(f.name),
                                       link.right.values.get(f.name))
            comparisons.append(comp)
            if not comp.within_tolerance:
                broke.append(f.name)
        return comparisons, broke

    def _compare_field(self, f: FieldConfig, lv: Any, rv: Any) -> FieldComparison:
        if f.dtype in (DataType.MONEY, DataType.NUMERIC):
            return self._compare_numeric(f, lv, rv)
        if f.dtype == DataType.DATE:
            return self._compare_date(f, lv, rv)
        return self._compare_text(f, lv, rv)

    def _compare_numeric(self, f, lv, rv) -> FieldComparison:
        if lv is None and rv is None:
            return FieldComparison(f.name, f.dtype.value, None, None, None, None, True)
        a = lv if isinstance(lv, Decimal) else Decimal(0)
        b = rv if isinstance(rv, Decimal) else Decimal(0)
        diff = a - b
        pct = float(diff / b) if b != 0 else (0.0 if diff == 0 else float("inf"))
        ok = abs(diff) <= f.abs_tol or (f.rel_tol > 0 and b != 0 and abs(pct) <= f.rel_tol)
        return FieldComparison(f.name, f.dtype.value, lv, rv, diff, pct, bool(ok))

    def _compare_date(self, f, lv, rv) -> FieldComparison:
        if lv is None and rv is None:
            return FieldComparison(f.name, f.dtype.value, None, None, None, None, True)
        if lv is None or rv is None:
            return FieldComparison(f.name, f.dtype.value, lv, rv, None, None, False)
        days = Decimal((lv - rv).days)
        ok = abs(days) <= f.abs_tol
        return FieldComparison(f.name, f.dtype.value, lv, rv, days, None, bool(ok))

    def _compare_text(self, f, lv, rv) -> FieldComparison:
        a = (lv or "").casefold() if isinstance(lv, str) else ""
        b = (rv or "").casefold() if isinstance(rv, str) else ""
        if f.text_fuzzy_threshold is not None and a and b:
            ok = string_similarity(a, b) >= f.text_fuzzy_threshold
        else:
            ok = a == b
        return FieldComparison(f.name, f.dtype.value, lv, rv, None, None, bool(ok))

    def _unmatched(self, r: CanonicalRecord, side: str) -> UnmatchedRecord:
        key_values = {k.name: r.values.get(k.name) for k in self._key_fields}
        return UnmatchedRecord(key=r.key, side=side, key_values=key_values,
                               values=r.values, source_files=r.source_files)
