"""Parser strategy interface + factory. Every parser takes (filename, bytes)."""
from __future__ import annotations

from typing import Dict, List, Protocol, Type

from ..models.documents import ExtractionResult, FinancialRecord, FinancialTable
from ..models.enums import FileFormat
from ..utils.errors import UnsupportedFormatError


class Parser(Protocol):
    """Strategy: parse raw bytes into a uniform ExtractionResult."""
    formats: List[FileFormat]

    def parse(self, filename: str, data: bytes) -> ExtractionResult: ...


def records_from_rows(rows: List[dict], columns: List[str], source_file: str,
                      table_name: str) -> List[FinancialRecord]:
    """Helper: build FinancialRecords from a list of row dicts."""
    out: List[FinancialRecord] = []
    for i, row in enumerate(rows):
        values = {c: row.get(c) for c in columns}
        out.append(FinancialRecord(values=values, source_file=source_file,
                                   table_name=table_name, row_index=i))
    return out


class ParserFactory:
    """Registers parsers by format and dispatches on filename."""

    def __init__(self) -> None:
        self._by_format: Dict[FileFormat, Parser] = {}

    def register(self, parser: Parser) -> "ParserFactory":
        for fmt in parser.formats:
            self._by_format[fmt] = parser
        return self

    def for_filename(self, filename: str) -> Parser:
        fmt = FileFormat.from_filename(filename)
        parser = self._by_format.get(fmt)
        if parser is None:
            raise UnsupportedFormatError(f"No parser registered for {fmt.value}")
        return parser


def default_factory() -> ParserFactory:
    """Wire up all built-in parsers."""
    from .csv_parser import CsvParser
    from .txt_parser import TxtTableParser
    from .excel_parser import ExcelParser
    from .docx_parser import DocxParser
    from .pdf_parser import PdfParser

    return (ParserFactory()
            .register(CsvParser())
            .register(TxtTableParser())
            .register(ExcelParser())
            .register(DocxParser())
            .register(PdfParser()))
