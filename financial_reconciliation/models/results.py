"""Canonical records, match/reconciliation results, and the session accumulator."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .documents import ExtractionResult
from .enums import MatchType, RecordStatus


@dataclass(frozen=True)
class CanonicalRecord:
    """A side's row after column mapping, normalization, and key aggregation."""
    key: str                         # composite key string
    key_parts: Tuple[Any, ...]
    values: Dict[str, Any]           # canonical field -> normalized value (Decimal/date/str)
    source_files: str
    row_count: int


@dataclass(frozen=True)
class StrategyScore:
    strategy: MatchType
    score: float                     # 0..1
    weight: float


@dataclass(frozen=True)
class FieldComparison:
    field: str
    dtype: str
    left_value: Any
    right_value: Any
    difference: Optional[Decimal]
    pct_difference: Optional[float]
    within_tolerance: bool


@dataclass(frozen=True)
class Match:
    left_key: str
    right_key: str
    match_type: MatchType
    confidence: float                # 0..1 weighted
    strategy_scores: List[StrategyScore]
    explanation: str
    field_comparisons: List[FieldComparison]
    status: RecordStatus
    break_fields: List[str]
    key_values: Dict[str, Any]
    left_source_files: str
    right_source_files: str


@dataclass(frozen=True)
class UnmatchedRecord:
    key: str
    side: str
    key_values: Dict[str, Any]
    values: Dict[str, Any]
    source_files: str


@dataclass(frozen=True)
class FieldVariance:
    field: str
    dtype: str
    sum_left_minus_right: Optional[Decimal]
    sum_abs_difference: Optional[Decimal]
    n_breaks: int


@dataclass(frozen=True)
class ReconciliationResult:
    reconciled: List[Match]
    breaks: List[Match]
    unmatched_left: List[UnmatchedRecord]
    unmatched_right: List[UnmatchedRecord]
    field_variance: List[FieldVariance]
    summary: Dict[str, Any]


@dataclass(frozen=True)
class ReconciliationSession:
    """Immutable accumulator. Stages return a *new* session, never mutate one."""
    session_id: str
    left_extractions: Tuple[ExtractionResult, ...] = ()
    right_extractions: Tuple[ExtractionResult, ...] = ()
    result: Optional[ReconciliationResult] = None

    def with_extractions(self, side: str, extractions: List[ExtractionResult]) -> "ReconciliationSession":
        if side == "left":
            return replace(self, left_extractions=self.left_extractions + tuple(extractions))
        return replace(self, right_extractions=self.right_extractions + tuple(extractions))

    def cleared_side(self, side: str) -> "ReconciliationSession":
        if side == "left":
            return replace(self, left_extractions=())
        return replace(self, right_extractions=())

    def with_result(self, result: ReconciliationResult) -> "ReconciliationSession":
        return replace(self, result=result)

    def columns(self, side: str) -> List[str]:
        exts = self.left_extractions if side == "left" else self.right_extractions
        seen: List[str] = []
        for e in exts:
            for c in e.all_columns():
                if c not in seen:
                    seen.append(c)
        return seen
