"""Engine exception hierarchy."""
from __future__ import annotations


class ReconciliationError(Exception):
    """Base for all engine errors."""


class ParserError(ReconciliationError):
    """A file could not be parsed."""


class UnsupportedFormatError(ParserError):
    """No parser is registered for the file's format."""


class ConfigurationError(ReconciliationError):
    """Invalid or incomplete engine configuration."""


class MatchingError(ReconciliationError):
    """Failure during candidate generation or matching."""
