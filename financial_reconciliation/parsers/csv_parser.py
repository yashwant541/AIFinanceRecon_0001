"""CSV / TSV parser. Reads the full grid (no header assumption) and defers
header-row and table-region detection to the extraction layer.
"""
from __future__ import annotations

import csv
import io
from typing import List

from ..extraction.table_detection import tables_from_grid
from ..models.documents import (ExtractionResult, FinancialDocument, FinancialTable,
                                 ParseWarning)
from ..models.enums import FileFormat, Severity, WarningCode


def _decode(data: bytes, warnings: List[ParseWarning]):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    warnings.append(ParseWarning(WarningCode.DECODE_FALLBACK,
                                 "Falling back to latin-1 with replacement.", Severity.WARNING))
    return data.decode("latin-1", errors="replace"), "latin-1"


def _dedupe(header: List[str]) -> List[str]:
    seen, out = {}, []
    for h in header:
        if h in seen:
            seen[h] += 1; out.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0; out.append(h)
    return out


def _empty(filename: str, fmt: FileFormat, warnings: List[ParseWarning]) -> ExtractionResult:
    warnings.append(ParseWarning(WarningCode.EMPTY_DOCUMENT,
                                 f"{filename} contained no readable rows.", Severity.WARNING))
    return ExtractionResult(FinancialDocument(filename, fmt, []), warnings, {"rows": 0})


class CsvParser:
    formats = [FileFormat.CSV]

    def parse(self, filename: str, data: bytes) -> ExtractionResult:
        warnings: List[ParseWarning] = []
        text, enc = _decode(data, warnings)
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = "\t" if filename.lower().endswith(".tsv") else ","

        grid = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
        if not any(any(str(c).strip() for c in row) for row in grid):
            return _empty(filename, FileFormat.CSV, warnings)

        tables = tables_from_grid(grid, filename, "csv")
        doc = FinancialDocument(filename, FileFormat.CSV, tables,
                                metadata={"encoding": enc, "delimiter": delimiter})
        return ExtractionResult(doc, warnings,
                                {"tables": len(tables), "rows": doc.record_count})
