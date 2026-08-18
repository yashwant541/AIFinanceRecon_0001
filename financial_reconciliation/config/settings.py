"""Typed, serializable configuration. Nothing hardcoded lives in logic modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..models.enums import AggFunc, DataType, FieldRole
from ..utils.errors import ConfigurationError


@dataclass(frozen=True)
class FieldConfig:
    name: str
    role: FieldRole
    dtype: DataType
    left_source: Optional[str] = None
    right_source: Optional[str] = None
    abs_tol: Decimal = Decimal("0")
    rel_tol: float = 0.0                       # fraction, 0.01 = 1%
    text_fuzzy_threshold: Optional[float] = None  # 0..100
    agg: AggFunc = AggFunc.SUM
    match_weight: float = 1.0                  # contribution to key-matching text

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FieldConfig":
        try:
            return FieldConfig(
                name=d["name"].strip(),
                role=FieldRole(d.get("role", "value")),
                dtype=DataType(d.get("dtype", "text")),
                left_source=d.get("left_source") or None,
                right_source=d.get("right_source") or None,
                abs_tol=Decimal(str(d.get("abs_tol", "0") or "0")),
                rel_tol=float(d.get("rel_tol", 0) or 0),
                text_fuzzy_threshold=(
                    float(d["text_fuzzy_threshold"])
                    if d.get("text_fuzzy_threshold") not in (None, "") else None),
                agg=AggFunc(d.get("agg", "sum")),
                match_weight=float(d.get("match_weight", 1.0) or 1.0),
            )
        except (KeyError, ValueError) as exc:
            raise ConfigurationError(f"Invalid field config {d!r}: {exc}") from exc


@dataclass(frozen=True)
class NormalizationConfig:
    casefold_keys: bool = True
    drop_exact_duplicates: bool = True
    dayfirst: bool = False
    decimal_places: int = 2
    strip_non_english: bool = False   # drop non-Latin-script characters
    null_tokens: tuple = ("", "na", "n/a", "nan", "none", "null", "-")


@dataclass(frozen=True)
class MatchingConfig:
    fuzzy_enabled: bool = True
    fuzzy_threshold: float = 90.0              # 0..100 min composite-key similarity
    semantic_enabled: bool = False
    semantic_threshold: float = 75.0
    numeric_enabled: bool = False              # use value-field proximity as a signal
    blocking_field: Optional[str] = None
    blocking_prefix_len: int = 0
    weight_exact: float = 1.0
    weight_fuzzy: float = 0.8
    weight_semantic: float = 0.7
    weight_numeric: float = 0.5
    accept_threshold: float = 0.6              # min weighted confidence to accept a non-exact match

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MatchingConfig":
        base = MatchingConfig()
        return MatchingConfig(
            fuzzy_enabled=bool(d.get("fuzzy_enabled", base.fuzzy_enabled)),
            fuzzy_threshold=float(d.get("fuzzy_threshold", base.fuzzy_threshold)),
            semantic_enabled=bool(d.get("semantic_enabled", base.semantic_enabled)),
            semantic_threshold=float(d.get("semantic_threshold", base.semantic_threshold)),
            numeric_enabled=bool(d.get("numeric_enabled", base.numeric_enabled)),
            blocking_field=d.get("blocking_field") or None,
            blocking_prefix_len=int(d.get("blocking_prefix_len", 0) or 0),
            accept_threshold=float(d.get("accept_threshold", base.accept_threshold)),
        )


@dataclass(frozen=True)
class EngineConfig:
    fields: List[FieldConfig]
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)

    def key_fields(self) -> List[FieldConfig]:
        return [f for f in self.fields if f.role == FieldRole.KEY]

    def value_fields(self) -> List[FieldConfig]:
        return [f for f in self.fields if f.role == FieldRole.VALUE]

    def validate(self) -> None:
        if not self.fields:
            raise ConfigurationError("No fields configured.")
        if not self.key_fields():
            raise ConfigurationError("At least one key field is required.")
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise ConfigurationError("Duplicate canonical field names.")

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "EngineConfig":
        cfg = EngineConfig(
            fields=[FieldConfig.from_dict(f) for f in d.get("fields", [])],
            normalization=NormalizationConfig(**{
                k: v for k, v in d.get("norm", {}).items()
                if k in NormalizationConfig.__dataclass_fields__}),
            matching=MatchingConfig.from_dict(d.get("matching", {})),
        )
        cfg.validate()
        return cfg
