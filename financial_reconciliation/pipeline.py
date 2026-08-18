"""End-to-end orchestration: Upload -> Parse -> Normalize -> Match -> Reconcile."""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .config.settings import EngineConfig
from .matching.matcher import Matcher
from .models.documents import ExtractionResult, UploadedDocument
from .models.enums import Side
from .models.results import ReconciliationResult
from .normalization.normalizer import Normalizer
from .parsers.base import ParserFactory, default_factory
from .reconciliation.reconciler import Reconciler
from .utils.logging import get_logger

log = get_logger("pipeline")


class ReconciliationPipeline:
    """Reusable, framework-free. The webapp holds one of these."""

    def __init__(self, parser_factory: ParserFactory | None = None) -> None:
        self._parsers = parser_factory or default_factory()

    # -- parsing ------------------------------------------------------------
    def parse_documents(self, docs: Iterable[UploadedDocument]) -> List[ExtractionResult]:
        results: List[ExtractionResult] = []
        for doc in docs:
            parser = self._parsers.for_filename(doc.filename)
            result = parser.parse(doc.filename, doc.data)
            log.info("parsed %s: %d tables, %d rows, %d warnings",
                     doc.filename, len(result.document.tables),
                     result.document.record_count, len(result.warnings))
            results.append(result)
        return results

    @staticmethod
    def columns(extractions: Iterable[ExtractionResult]) -> List[str]:
        seen: List[str] = []
        for e in extractions:
            for c in e.all_columns():
                if c not in seen:
                    seen.append(c)
        return seen

    @staticmethod
    def _records(extractions: List[ExtractionResult], included: set | None):
        out = []
        for e in extractions:
            for r in e.all_records():
                if included is None or f"{r.source_file}||{r.table_name}" in included:
                    out.append(r)
        return out

    # -- reconcile ----------------------------------------------------------
    def reconcile(self,
                  left: List[ExtractionResult],
                  right: List[ExtractionResult],
                  config: EngineConfig,
                  included_left: set | None = None,
                  included_right: set | None = None,
                  ontology=None) -> ReconciliationResult:
        config.validate()
        normalizer = Normalizer(config, ontology=ontology)

        left_records = self._records(left, included_left)
        right_records = self._records(right, included_right)
        left_canon = normalizer.canonicalize(left_records, Side.LEFT)
        right_canon = normalizer.canonicalize(right_records, Side.RIGHT)

        matcher = Matcher(config)
        links, un_left, un_right = matcher.match(left_canon, right_canon)

        reconciler = Reconciler(config)
        result = reconciler.reconcile(
            links, un_left, un_right,
            n_left=len(left_canon), n_right=len(right_canon),
            fuzzy_backend=matcher.fuzzy_backend)
        log.info("reconciled: %s", {k: result.summary[k] for k in
                                    ("reconciled", "breaks", "unmatched_left", "unmatched_right")})
        return result
