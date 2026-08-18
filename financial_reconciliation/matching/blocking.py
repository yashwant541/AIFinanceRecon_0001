"""Blocking: bucket residual records so fuzzy/semantic matching avoids O(n*m)."""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..config.settings import MatchingConfig
from ..models.results import CanonicalRecord


def build_blocks(
    left: List[CanonicalRecord],
    right: List[CanonicalRecord],
    cfg: MatchingConfig,
) -> List[Tuple[List[CanonicalRecord], List[CanonicalRecord]]]:
    """Return list of (left_bucket, right_bucket) candidate pairs to compare."""
    if cfg.blocking_field:
        return _bucket(left, right, lambda r: _norm(r.values.get(cfg.blocking_field)))
    if cfg.blocking_prefix_len > 0:
        n = cfg.blocking_prefix_len
        return _bucket(left, right, lambda r: r.key[:n])
    return [(left, right)]  # single global block


def _norm(v) -> str:
    return "" if v is None else str(v)


def _bucket(left, right, key_fn):
    buckets: Dict[str, Tuple[List, List]] = {}
    for r in left:
        buckets.setdefault(key_fn(r), ([], []))[0].append(r)
    for r in right:
        buckets.setdefault(key_fn(r), ([], []))[1].append(r)
    return [(l, r) for (l, r) in buckets.values() if l and r]
