"""Semantic similarity via TF-IDF cosine.

Uses scikit-learn if available; otherwise a compact NumPy TF-IDF so the feature
works offline with no heavy dependency. Returns similarities on a 0..100 scale.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _tok(s: str) -> List[str]:
    return _TOKEN.findall((s or "").lower())


try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SK = True
except Exception:  # pragma: no cover
    _SK = False


class SemanticIndex:
    """Index a corpus (right side) and score queries (left side) against it."""

    def __init__(self, corpus: List[str]) -> None:
        self._corpus = corpus
        self._enabled = bool(corpus)
        if not self._enabled:
            return
        if _SK:
            self._vec = TfidfVectorizer(analyzer="word", token_pattern=r"[A-Za-z0-9]+")
            self._matrix = self._vec.fit_transform(corpus)
            self._mode = "sklearn"
        else:
            self._build_numpy(corpus)
            self._mode = "numpy"

    # --- pure-numpy fallback ----------------------------------------------
    def _build_numpy(self, corpus: List[str]) -> None:
        docs = [_tok(c) for c in corpus]
        df: Counter = Counter()
        for d in docs:
            for term in set(d):
                df[term] += 1
        n = len(docs)
        self._idf: Dict[str, float] = {t: math.log((1 + n) / (1 + c)) + 1.0
                                       for t, c in df.items()}
        self._doc_vecs = [self._vectorize(d) for d in docs]

    def _vectorize(self, tokens: List[str]) -> Dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        vec = {t: (cnt / len(tokens)) * self._idf.get(t, 0.0) for t, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    @staticmethod
    def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        small, big = (a, b) if len(a) < len(b) else (b, a)
        return sum(v * big.get(t, 0.0) for t, v in small.items())

    # --- query ------------------------------------------------------------
    def best_match(self, query: str) -> tuple[Optional[int], float]:
        """Return (corpus_index, similarity 0..100) for the closest doc."""
        if not self._enabled:
            return None, 0.0
        if self._mode == "sklearn":
            qv = self._vec.transform([query])
            sims = cosine_similarity(qv, self._matrix)[0]
            idx = int(sims.argmax())
            return idx, float(sims[idx]) * 100.0
        qvec = self._vectorize(_tok(query))
        best_i, best_s = None, 0.0
        for i, dv in enumerate(self._doc_vecs):
            s = self._cos(qvec, dv)
            if s > best_s:
                best_i, best_s = i, s
        return best_i, best_s * 100.0
