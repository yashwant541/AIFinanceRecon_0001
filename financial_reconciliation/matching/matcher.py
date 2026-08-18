"""Match left canonical records against right, with an explained confidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..config.settings import EngineConfig
from ..models.enums import DataType, MatchType
from ..models.results import CanonicalRecord, StrategyScore
from ..utils.logging import get_logger
from .blocking import build_blocks
from .semantic import SemanticIndex
from .similarity import string_similarity, BACKEND

log = get_logger("matching")


@dataclass(frozen=True)
class MatchLink:
    left: CanonicalRecord
    right: CanonicalRecord
    match_type: MatchType
    confidence: float
    strategy_scores: List[StrategyScore]
    explanation: str


class Matcher:
    def __init__(self, config: EngineConfig) -> None:
        self._cfg = config
        self._m = config.matching
        self._key_fields = config.key_fields()
        self._numeric_value_fields = [
            f for f in config.value_fields()
            if f.dtype in (DataType.MONEY, DataType.NUMERIC)]

    @property
    def fuzzy_backend(self) -> str:
        return BACKEND

    def match(self, left: List[CanonicalRecord], right: List[CanonicalRecord]
              ) -> Tuple[List[MatchLink], List[CanonicalRecord], List[CanonicalRecord]]:
        links: List[MatchLink] = []
        used_left: set = set()
        used_right: set = set()
        right_by_key: Dict[str, CanonicalRecord] = {r.key: r for r in right}

        # 1) exact key match (fast, deterministic)
        for lr in left:
            rr = right_by_key.get(lr.key)
            if rr and lr.key not in used_left and rr.key not in used_right:
                links.append(MatchLink(
                    lr, rr, MatchType.EXACT, 1.0,
                    [StrategyScore(MatchType.EXACT, 1.0, self._m.weight_exact)],
                    "Exact composite-key match."))
                used_left.add(lr.key)
                used_right.add(rr.key)

        # 2) fuzzy / semantic / numeric on residuals, via blocking + greedy assignment
        res_left = [r for r in left if r.key not in used_left]
        res_right = [r for r in right if r.key not in used_right]
        if res_left and res_right and (self._m.fuzzy_enabled or self._m.semantic_enabled
                                       or self._m.numeric_enabled):
            candidates = self._score_candidates(res_left, res_right)
            candidates.sort(key=lambda c: c.confidence, reverse=True)
            for link in candidates:
                if link.left.key in used_left or link.right.key in used_right:
                    continue
                if link.confidence < self._m.accept_threshold:
                    continue
                links.append(link)
                used_left.add(link.left.key)
                used_right.add(link.right.key)

        unmatched_left = [r for r in left if r.key not in used_left]
        unmatched_right = [r for r in right if r.key not in used_right]
        return links, unmatched_left, unmatched_right

    # -- scoring ------------------------------------------------------------
    def _score_candidates(self, left, right) -> List[MatchLink]:
        blocks = build_blocks(left, right, self._m)
        out: List[MatchLink] = []
        for lbucket, rbucket in blocks:
            sem_index = (SemanticIndex([r.key for r in rbucket])
                         if self._m.semantic_enabled else None)
            for lr in lbucket:
                sem_hit = sem_index.best_match(lr.key) if sem_index else (None, 0.0)
                for rr in rbucket:
                    link = self._score_pair(lr, rr, rbucket, sem_hit)
                    if link is not None:
                        out.append(link)
        return out

    def _score_pair(self, lr, rr, rbucket, sem_hit) -> Optional[MatchLink]:
        scores: List[StrategyScore] = []
        reasons: List[str] = []

        if self._m.fuzzy_enabled:
            fs = string_similarity(lr.key, rr.key)
            if fs >= self._m.fuzzy_threshold:
                scores.append(StrategyScore(MatchType.FUZZY, fs / 100.0, self._m.weight_fuzzy))
                reasons.append(f"fuzzy key {fs:.0f}%")

        if self._m.semantic_enabled:
            idx, ss = sem_hit
            if idx is not None and rbucket[idx].key == rr.key and ss >= self._m.semantic_threshold:
                scores.append(StrategyScore(MatchType.SEMANTIC, ss / 100.0, self._m.weight_semantic))
                reasons.append(f"semantic {ss:.0f}%")

        if self._m.numeric_enabled and self._numeric_value_fields:
            ns = self._numeric_proximity(lr, rr)
            if ns is not None:
                scores.append(StrategyScore(MatchType.NUMERIC, ns, self._m.weight_numeric))
                reasons.append(f"numeric proximity {ns * 100:.0f}%")

        if not scores:
            return None

        wsum = sum(s.weight for s in scores) or 1.0
        confidence = sum(s.score * s.weight for s in scores) / wsum
        dominant = max(scores, key=lambda s: s.score * s.weight).strategy
        explanation = "Matched on " + ", ".join(reasons) + \
            f" (confidence {confidence * 100:.0f}%)."
        return MatchLink(lr, rr, dominant, round(confidence, 4), scores, explanation)

    def _numeric_proximity(self, lr, rr) -> Optional[float]:
        sims: List[float] = []
        for f in self._numeric_value_fields:
            a, b = lr.values.get(f.name), rr.values.get(f.name)
            if not isinstance(a, Decimal) or not isinstance(b, Decimal):
                continue
            scale = max(abs(a), abs(b), Decimal(1))
            sims.append(float(max(Decimal(0), Decimal(1) - abs(a - b) / scale)))
        if not sims:
            return None
        return sum(sims) / len(sims)
