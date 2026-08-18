"""Synonym / ontology support.

Lets "NII", "Non-Interest Income" and "Non Interest Income Islamic Banking" all
resolve to one canonical concept so they reconcile as the same line item. The
list is data, not code: users upload it and can update it any time.

Accepted upload formats:
  * JSON  {"Non-Interest Income": ["NII", "Non Interest Income Islamic Banking"]}
          or [["Non-Interest Income", "NII", ...], ["Operating income", ...]]
  * CSV   one synonym group per row; first cell is the canonical term
  * TXT   one group per line, members separated by "|" or ","
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Dict, Iterable, List, Optional

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", str(s).strip().casefold())


class Ontology:
    """Maps a normalized alias -> canonical term."""

    def __init__(self, alias_to_canonical: Optional[Dict[str, str]] = None) -> None:
        self._map: Dict[str, str] = dict(alias_to_canonical or {})

    # -- construction -------------------------------------------------------
    @classmethod
    def from_groups(cls, groups: Iterable) -> "Ontology":
        mapping: Dict[str, str] = {}
        if isinstance(groups, dict):
            items = [[canon, *aliases] for canon, aliases in groups.items()]
        else:
            items = [list(g) for g in groups]
        for group in items:
            members = [m for m in group if str(m).strip()]
            if not members:
                continue
            canonical = str(members[0]).strip()
            for member in members:
                mapping[_norm(member)] = canonical
        return cls(mapping)

    @classmethod
    def from_file(cls, filename: str, data: bytes) -> "Ontology":
        text = data.decode("utf-8-sig", errors="replace")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
        if ext == "json":
            return cls.from_groups(json.loads(text))
        if ext in ("csv", "tsv"):
            delim = "\t" if ext == "tsv" else ","
            rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
            return cls.from_groups(rows)
        # txt: one group per line
        groups = [re.split(r"[|,]", ln) for ln in text.splitlines() if ln.strip()]
        return cls.from_groups(groups)

    # -- use ----------------------------------------------------------------
    def canonical(self, text) -> str:
        """Return the canonical concept for a value (or the value unchanged)."""
        if text is None:
            return ""
        return self._map.get(_norm(text), str(text).strip())

    def merge(self, other: "Ontology") -> "Ontology":
        merged = dict(self._map)
        merged.update(other._map)
        return Ontology(merged)

    @property
    def size(self) -> int:
        return len(self._map)

    def groups(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for alias, canon in self._map.items():
            out.setdefault(canon, []).append(alias)
        return out
