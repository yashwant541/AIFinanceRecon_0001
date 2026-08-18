"""Turn raw FinancialRecords into normalized, key-aggregated CanonicalRecords."""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd

from ..config.settings import EngineConfig, FieldConfig, NormalizationConfig
from ..models.enums import AggFunc, DataType, FieldRole, Side
from ..models.money import parse_decimal
from ..models.results import CanonicalRecord

_WS = re.compile(r"\s+")
_NON_LATIN = re.compile(r"[^\x00-\u024F]+")   # keep Basic Latin + Latin Extended-A


class Normalizer:
    def __init__(self, config: EngineConfig, ontology=None) -> None:
        self._cfg = config
        self._norm = config.normalization
        self._ontology = ontology

    # -- value coercion -----------------------------------------------------
    def _coerce(self, field: FieldConfig, raw: Any) -> Any:
        if field.dtype in (DataType.MONEY, DataType.NUMERIC):
            return parse_decimal(raw, null_tokens=self._norm.null_tokens)
        if field.dtype == DataType.DATE:
            return self._parse_date(raw)
        return self._parse_text(raw, is_key=field.role == FieldRole.KEY)

    def _parse_text(self, raw: Any, is_key: bool) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip()
        if self._norm.strip_non_english:
            s = _NON_LATIN.sub(" ", s).strip()
        if s == "" or s.lower() in self._norm.null_tokens:
            return None
        s = _WS.sub(" ", s)
        if is_key and self._ontology is not None:
            s = self._ontology.canonical(s)          # collapse synonyms
        if is_key and self._norm.casefold_keys:
            s = s.casefold()
        return s

    def _parse_date(self, raw: Any) -> Optional[date]:
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return None
        ts = pd.to_datetime(raw, dayfirst=self._norm.dayfirst, errors="coerce")
        return None if pd.isna(ts) else ts.date()

    # -- pipeline -----------------------------------------------------------
    def canonicalize(self, records: List[Any], side: Side) -> List[CanonicalRecord]:
        key_fields = self._cfg.key_fields()
        value_fields = self._cfg.value_fields()
        side_name = side.value

        normalized_rows: List[Dict[str, Any]] = []
        provenance: List[str] = []
        for rec in records:
            row: Dict[str, Any] = {}
            for field in self._cfg.fields:
                src = field.left_source if side_name == "left" else field.right_source
                raw = rec.values.get(src) if src else None
                row[field.name] = self._coerce(field, raw)
            # skip rows whose keys are entirely empty
            if all(row[k.name] is None for k in key_fields):
                continue
            normalized_rows.append(row)
            provenance.append(rec.source_file)

        if not normalized_rows:
            return []

        if self._norm.drop_exact_duplicates:
            normalized_rows, provenance = _dedupe(normalized_rows, provenance)

        return self._aggregate(normalized_rows, provenance, key_fields, value_fields)

    def _aggregate(self, rows, provenance, key_fields, value_fields) -> List[CanonicalRecord]:
        buckets: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        for row, src in zip(rows, provenance):
            parts = tuple("" if row[k.name] is None else str(row[k.name]) for k in key_fields)
            key = "|".join(parts)
            b = buckets.get(key)
            if b is None:
                b = {"key_parts": tuple(row[k.name] for k in key_fields),
                     "rows": [], "files": []}
                buckets[key] = b
            b["rows"].append(row)
            b["files"].append(src)

        out: List[CanonicalRecord] = []
        for key, b in buckets.items():
            values: Dict[str, Any] = {}
            for kf in key_fields:
                values[kf.name] = b["rows"][0][kf.name]
            for vf in value_fields:
                values[vf.name] = _agg_values([r[vf.name] for r in b["rows"]], vf)
            out.append(CanonicalRecord(
                key=key, key_parts=b["key_parts"], values=values,
                source_files=", ".join(sorted(set(b["files"]))),
                row_count=len(b["rows"])))
        return out


def _dedupe(rows, provenance):
    seen = set()
    out_rows, out_prov = [], []
    for row, src in zip(rows, provenance):
        sig = tuple(sorted((k, str(v)) for k, v in row.items()))
        if sig in seen:
            continue
        seen.add(sig)
        out_rows.append(row)
        out_prov.append(src)
    return out_rows, out_prov


def _agg_values(vals: List[Any], field: FieldConfig) -> Any:
    present = [v for v in vals if v is not None]
    if field.dtype in (DataType.MONEY, DataType.NUMERIC):
        nums: List[Decimal] = [v for v in present if isinstance(v, Decimal)]
        if field.agg == AggFunc.COUNT:
            return Decimal(len(present))
        if not nums:
            return None
        if field.agg == AggFunc.SUM:
            return sum(nums, Decimal(0))
        if field.agg == AggFunc.MEAN:
            return sum(nums, Decimal(0)) / Decimal(len(nums))
        if field.agg == AggFunc.MAX:
            return max(nums)
        if field.agg == AggFunc.MIN:
            return min(nums)
        if field.agg == AggFunc.LAST:
            return nums[-1]
        return nums[0]  # FIRST
    # text / date
    if not present:
        return None
    if field.agg == AggFunc.LAST:
        return present[-1]
    if field.agg == AggFunc.COUNT:
        return len(present)
    return present[0]  # FIRST / default
