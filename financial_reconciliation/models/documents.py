"""Rich domain objects produced by parsers.

    UploadedDocument -> (parser) -> ExtractionResult { FinancialDocument, warnings, stats }
    FinancialDocument -> FinancialTable[] -> FinancialRecord[]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .enums import FileFormat, Severity, WarningCode


@dataclass(frozen=True)
class UploadedDocument:
    """A file as received: name + raw bytes. Never a path."""
    filename: str
    data: bytes

    @property
    def file_format(self) -> FileFormat:
        return FileFormat.from_filename(self.filename)

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class ParseWarning:
    code: WarningCode
    message: str
    severity: Severity = Severity.WARNING
    locator: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code.value, "message": self.message,
                "severity": self.severity.value, "locator": self.locator}


@dataclass(frozen=True)
class FinancialRecord:
    """One row of tabular data with provenance."""
    values: Dict[str, Any]
    source_file: str
    table_name: str
    row_index: int


@dataclass
class FinancialTable:
    name: str
    columns: List[str]
    records: List[FinancialRecord]
    source_file: str

    @property
    def row_count(self) -> int:
        return len(self.records)


@dataclass
class FinancialDocument:
    filename: str
    file_format: FileFormat
    tables: List[FinancialTable] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return sum(t.row_count for t in self.tables)


@dataclass
class ExtractionResult:
    """Uniform parser output."""
    document: FinancialDocument
    warnings: List[ParseWarning] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def all_records(self) -> List[FinancialRecord]:
        out: List[FinancialRecord] = []
        for t in self.document.tables:
            out.extend(t.records)
        return out

    def all_columns(self) -> List[str]:
        """Union of column names across every table, order-preserving."""
        seen: List[str] = []
        for t in self.document.tables:
            for c in t.columns:
                if c not in seen:
                    seen.append(c)
        return seen

    @property
    def has_data(self) -> bool:
        return self.document.record_count > 0
