"""Plain-text table parser (pipe / tab / multi-space aligned). Builds a grid and
defers header/region detection to the extraction layer.
"""
from __future__ import annotations

import re
from typing import Callable, List, Tuple

from ..extraction.table_detection import tables_from_grid
from ..models.documents import ExtractionResult, FinancialDocument, ParseWarning
from ..models.enums import FileFormat
from .csv_parser import _decode, _empty

_SEP_ROW = re.compile(r"^[\s|:+\-]+$")


class TxtTableParser:
    formats = [FileFormat.TXT]

    def parse(self, filename: str, data: bytes) -> ExtractionResult:
        warnings: List[ParseWarning] = []
        text, enc = _decode(data, warnings)
        lines = [ln for ln in text.splitlines() if ln.strip() and not _SEP_ROW.match(ln)]
        if not lines:
            return _empty(filename, FileFormat.TXT, warnings)

        split, mode = self._detect(lines[0])
        grid = [[c.strip() for c in split(ln)] for ln in lines]
        tables = tables_from_grid(grid, filename, "txt")
        doc = FinancialDocument(filename, FileFormat.TXT, tables,
                                metadata={"encoding": enc, "layout": mode})
        return ExtractionResult(doc, warnings,
                                {"tables": len(tables), "rows": doc.record_count})

    def _detect(self, head: str) -> Tuple[Callable[[str], List[str]], str]:
        if "|" in head:
            return (lambda s: s.strip().strip("|").split("|")), "pipe"
        if "\t" in head:
            return (lambda s: s.split("\t")), "tab"
        return (lambda s: re.split(r"\s{2,}", s.strip())), "aligned"
