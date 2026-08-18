"""String similarity. Uses rapidfuzz when available, else stdlib difflib."""
from __future__ import annotations

try:
    from rapidfuzz import fuzz as _rf

    BACKEND = "rapidfuzz"

    def string_similarity(a: str, b: str) -> float:
        """0..100."""
        return float(_rf.token_sort_ratio(a or "", b or ""))

except Exception:  # pragma: no cover
    from difflib import SequenceMatcher

    BACKEND = "difflib"

    def string_similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a or "", b or "").ratio() * 100.0
