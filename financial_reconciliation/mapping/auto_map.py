"""Suggest a canonical field mapping by aligning left and right column profiles.

Column pairs are scored on three complementary signals, which makes the mapping
robust to renamed columns:
  * value overlap (Jaccard of the two columns' value sets) — strongest signal;
  * a financial synonym dictionary (invoice~reference, amount~total, ...);
  * raw column-name similarity.
Proposes key vs value roles and guarantees at least one key.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..extraction.profiling import ColumnProfile
from ..matching.similarity import string_similarity
from ..models.enums import DataType, FieldRole

_CLEAN = re.compile(r"[^a-z0-9]+")

# canonical concept -> aliases (extend freely; this is the ontology seed)
_SYNONYMS: Dict[str, List[str]] = {
    "invoice": ["invoice", "inv", "reference", "ref", "document", "doc", "bill", "voucher"],
    "account": ["account", "acct", "acc", "gl", "ledger"],
    "id": ["id", "code", "number", "no", "num", "key", "sku", "isin", "cusip"],
    "amount": ["amount", "amt", "total", "value", "balance", "sum", "net", "gross",
               "debit", "credit", "charge", "price", "cost"],
    "date": ["date", "dt", "posted", "due", "period", "asof"],
    "vendor": ["vendor", "supplier", "payee", "counterparty", "merchant", "party", "customer"],
    "description": ["description", "desc", "narrative", "details", "memo", "particulars"],
    "quantity": ["quantity", "qty", "units", "count"],
    "currency": ["currency", "ccy", "curr"],
}
_CONCEPT_OF: Dict[str, str] = {a: c for c, al in _SYNONYMS.items() for a in al}


def _norm(name: str) -> str:
    return _CLEAN.sub(" ", name.lower()).strip()


def _tokens(name: str) -> List[str]:
    return [t for t in _norm(name).split() if t]


def _concepts(name: str) -> set:
    return {_CONCEPT_OF[t] for t in _tokens(name) if t in _CONCEPT_OF}


def _synonym_score(a: str, b: str) -> float:
    ca, cb = _concepts(a), _concepts(b)
    return 1.0 if ca and cb and (ca & cb) else 0.0


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if (a | b) else 0.0


def _canonical_name(left: str, right: str) -> str:
    for src in (left, right):
        for t in _tokens(src):
            if t in _CONCEPT_OF:
                return _CONCEPT_OF[t]
    base = _norm(left) or _norm(right)
    return _CLEAN.sub("_", base).strip("_") or "field"


def _type_compatible(a: DataType, b: DataType) -> bool:
    num = {DataType.MONEY, DataType.NUMERIC}
    return a == b or (a in num and b in num)


def _reconcile_dtype(a: DataType, b: DataType) -> DataType:
    num = {DataType.MONEY, DataType.NUMERIC}
    if a in num and b in num:
        return DataType.MONEY if DataType.MONEY in (a, b) else DataType.NUMERIC
    return a if a == b else DataType.TEXT


def _pair_score(lp: ColumnProfile, rp: ColumnProfile) -> float:
    if not _type_compatible(lp.dtype, rp.dtype):
        return 0.0
    name = string_similarity(_norm(lp.name), _norm(rp.name)) / 100.0
    syn = _synonym_score(lp.name, rp.name)
    overlap = _jaccard(lp.value_set, rp.value_set)
    return 0.30 * name + 0.30 * syn + 0.55 * overlap


def suggest_mapping(left: List[ColumnProfile], right: List[ColumnProfile],
                    threshold: float = 0.28) -> List[Dict[str, Any]]:
    # score every compatible pair, then assign greedily by best score
    scored: List[Tuple[float, ColumnProfile, ColumnProfile]] = []
    for lp in left:
        for rp in right:
            s = _pair_score(lp, rp)
            if s >= threshold:
                scored.append((s, lp, rp))
    scored.sort(key=lambda x: x[0], reverse=True)

    used_left, used_right = set(), set()
    fields: List[Dict[str, Any]] = []
    for score, lp, rp in scored:
        if lp.name in used_left or rp.name in used_right:
            continue
        used_left.add(lp.name); used_right.add(rp.name)
        dtype = _reconcile_dtype(lp.dtype, rp.dtype)
        is_key = (lp.role == FieldRole.KEY or rp.role == FieldRole.KEY) and dtype != DataType.MONEY
        field: Dict[str, Any] = {
            "name": _canonical_name(lp.name, rp.name),
            "role": "key" if is_key else "value",
            "dtype": dtype.value,
            "left_source": lp.name, "right_source": rp.name,
            "agg": "sum" if dtype in (DataType.MONEY, DataType.NUMERIC) else "first",
            "_confidence": round(score * 100, 1),
        }
        if dtype == DataType.MONEY:
            field["abs_tol"] = "0.01"
        if dtype == DataType.TEXT and not is_key:
            field["text_fuzzy_threshold"] = 85
        fields.append(field)

    # de-duplicate canonical names
    seen: Dict[str, int] = {}
    for f in fields:
        base = f["name"]
        if base in seen:
            seen[base] += 1; f["name"] = f"{base}_{seen[base]}"
        else:
            seen[base] = 0

    # ensure at least one key
    if fields and not any(f["role"] == "key" for f in fields):
        keyish = max(fields, key=lambda f: _uniq(f["left_source"], left))
        keyish["role"] = "key"
        if keyish["dtype"] == "money":
            keyish["dtype"] = "text"
    return fields


def _uniq(name: str, profiles: List[ColumnProfile]) -> float:
    for p in profiles:
        if p.name == name:
            return p.uniqueness
    return 0.0
