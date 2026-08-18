"""Enumerations shared across the reconciliation engine."""
from __future__ import annotations

from enum import Enum


class FileFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"
    TXT = "txt"

    @classmethod
    def from_filename(cls, filename: str) -> "FileFormat":
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mapping = {
            "pdf": cls.PDF, "docx": cls.DOCX, "xlsx": cls.XLSX, "xlsm": cls.XLSX,
            "xls": cls.XLS, "csv": cls.CSV, "tsv": cls.CSV, "txt": cls.TXT, "text": cls.TXT,
        }
        if ext not in mapping:
            raise ValueError(f"Unsupported file extension: '{ext}' ({filename})")
        return mapping[ext]


class Side(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class FieldRole(str, Enum):
    KEY = "key"
    VALUE = "value"


class DataType(str, Enum):
    TEXT = "text"
    NUMERIC = "numeric"
    MONEY = "money"
    DATE = "date"


class AggFunc(str, Enum):
    SUM = "sum"
    MEAN = "mean"
    FIRST = "first"
    LAST = "last"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class MatchType(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NUMERIC = "numeric"
    SEMANTIC = "semantic"
    NONE = "none"


class RecordStatus(str, Enum):
    RECONCILED = "reconciled"
    BREAK = "break"
    UNMATCHED_LEFT = "unmatched_left"
    UNMATCHED_RIGHT = "unmatched_right"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningCode(str, Enum):
    SCANNED_PDF = "scanned_pdf"
    ENCRYPTED_FILE = "encrypted_file"
    EMPTY_DOCUMENT = "empty_document"
    NO_TABLES_FOUND = "no_tables_found"
    PARSER_LIBRARY_MISSING = "parser_library_missing"
    AMBIGUOUS_DATE = "ambiguous_date"
    UNREADABLE_ROW = "unreadable_row"
    DECODE_FALLBACK = "decode_fallback"
