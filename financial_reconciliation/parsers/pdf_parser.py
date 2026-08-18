"""PDF parser (highest-risk format).

Extracts tables per page using two pdfplumber strategies and keeps whichever
yields more structure:
  * "lines"  -> ruled/lattice tables (explicit borders)
  * "text"   -> whitespace-aligned/borderless tables
Detects image-only (scanned) pages -> SCANNED_PDF warning (OCR out of scope v1),
handles encrypted files, and is import-guarded.
"""
from __future__ import annotations

import io
from typing import List

from ..extraction.pdf_financial import extract_financial_tables
from ..extraction.table_detection import tables_from_grid
from ..models.documents import (ExtractionResult, FinancialDocument, FinancialRecord,
                                 FinancialTable, ParseWarning)
from ..models.enums import FileFormat, Severity, WarningCode

try:
    import pdfplumber
    _PDF_OK = True
except Exception:  # pragma: no cover
    _PDF_OK = False

_LINES = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
_TEXT = {"vertical_strategy": "text", "horizontal_strategy": "text",
         "snap_tolerance": 4, "join_tolerance": 4}


class PdfParser:
    formats = [FileFormat.PDF]

    def parse(self, filename: str, data: bytes, pages=None) -> ExtractionResult:
        """`pages` = optional set/list of 1-based page numbers to read."""
        if not _PDF_OK:
            return _lib_missing(filename)
        wanted = set(int(p) for p in pages) if pages else None
        warnings: List[ParseWarning] = []
        tables: List[FinancialTable] = []
        try:
            pdf = pdfplumber.open(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001 (includes encrypted)
            warnings.append(ParseWarning(WarningCode.ENCRYPTED_FILE,
                                         f"Could not open {filename}: {exc}", Severity.ERROR))
            return ExtractionResult(FinancialDocument(filename, FileFormat.PDF, []), warnings)

        page_count = 0
        with pdf:
            page_count = len(pdf.pages)
            for p_idx, page in enumerate(pdf.pages):
                if wanted is not None and (p_idx + 1) not in wanted:
                    continue
                text = (page.extract_text() or "").strip()
                # 1) coordinate-based financial-table reconstruction (primary)
                fin = extract_financial_tables(page)
                if fin:
                    for t_idx, ft in enumerate(fin):
                        base = (ft.get("title")
                                or f"page{p_idx + 1}_table{t_idx + 1}").strip()
                        name = base
                        n = 1
                        while any(t.name == name for t in tables):
                            n += 1
                            name = f"{base} ({n})"
                        recs = [FinancialRecord(values=row, source_file=filename,
                                                table_name=name, row_index=i)
                                for i, row in enumerate(ft["rows"])]
                        tables.append(FinancialTable(name, ft["columns"], recs, filename))
                    continue
                # 2) fall back to ruled/whitespace grid detection
                grids = self._best_tables(page)
                if not text and not grids:
                    warnings.append(ParseWarning(
                        WarningCode.SCANNED_PDF,
                        f"Page {p_idx + 1} of {filename} has no extractable text "
                        "(likely scanned). OCR is not enabled.",
                        Severity.WARNING, {"page": p_idx + 1}))
                    continue
                for t_idx, grid in enumerate(grids):
                    tables.extend(tables_from_grid(
                        grid, filename, f"page{p_idx + 1}_t{t_idx + 1}"))

        if not tables and not any(w.code == WarningCode.SCANNED_PDF for w in warnings):
            warnings.append(ParseWarning(WarningCode.NO_TABLES_FOUND,
                                         f"No tables detected in {filename}.", Severity.WARNING))
        doc = FinancialDocument(filename, FileFormat.PDF, tables,
                                metadata={"pages": page_count})
        return ExtractionResult(doc, warnings, {"tables": len(tables), "rows": doc.record_count})

    @staticmethod
    def _best_tables(page) -> List[list]:
        """Fallback: ruled/lattice tables only. Whitespace-aligned tables are
        handled by the coordinate-based financial extractor, and running the
        'text' strategy here would mis-read prose as tables."""
        try:
            return page.extract_tables(table_settings=_LINES) or []
        except Exception:  # noqa: BLE001
            return []


def _lib_missing(filename: str) -> ExtractionResult:
    w = ParseWarning(WarningCode.PARSER_LIBRARY_MISSING,
                     "pdfplumber is not installed in this code env; "
                     f"{filename} was skipped. Add 'pdfplumber' to requirements.",
                     Severity.ERROR)
    return ExtractionResult(FinancialDocument(filename, FileFormat.PDF, []), [w], {"rows": 0})
