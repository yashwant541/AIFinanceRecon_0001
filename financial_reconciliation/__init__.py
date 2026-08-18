"""FinanceReconAI — enterprise financial reconciliation engine (framework-free)."""
from .pipeline import ReconciliationPipeline
from .config.settings import (EngineConfig, FieldConfig, MatchingConfig,
                              NormalizationConfig)
from .models.documents import UploadedDocument
from .models.enums import AggFunc, DataType, FieldRole, Side

__all__ = [
    "ReconciliationPipeline", "EngineConfig", "FieldConfig", "MatchingConfig",
    "NormalizationConfig", "UploadedDocument", "AggFunc", "DataType", "FieldRole", "Side",
]
__version__ = "1.0.0"
