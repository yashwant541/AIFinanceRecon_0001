"""Detect which row of a grid is the header — it need not be row 0.

Scores each candidate row on how "header-like" it is (mostly non-empty text,
distinct labels) versus how "data-like" the rows beneath it are (filled,
type-consistent, numeric). Handles preamble/title rows above the real header.
"""
from __future__ import annotations

from typing import List

from .grids import Grid, is_empty, is_number, is_texty, cell_str


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _header_likeness(row) -> float:
    nonempty = [c for c in row if not is_empty(c)]
    if len(nonempty) < 2:
        return -1.0
    frac_nonempty = len(nonempty) / max(len(row), 1)
    frac_text = _mean([1.0 if is_texty(c) else 0.0 for c in nonempty])
    labels = [cell_str(c).lower() for c in nonempty]
    uniqueness = len(set(labels)) / len(labels)
    frac_number = _mean([1.0 if is_number(c) else 0.0 for c in nonempty])
    return frac_nonempty + 1.2 * frac_text + uniqueness - 1.0 * frac_number


def _data_likeness(grid: Grid, start: int, lookahead: int = 8) -> float:
    below = grid[start:start + lookahead]
    if not below:
        return -1.0
    fills, nums = [], []
    for row in below:
        cells = row
        fills.append(_mean([0.0 if is_empty(c) else 1.0 for c in cells]))
        present = [c for c in cells if not is_empty(c)]
        if present:
            nums.append(_mean([1.0 if is_number(c) else 0.0 for c in present]))
    return _mean(fills) + 0.6 * _mean(nums)


def detect_header_row(grid: Grid, max_scan: int = 25) -> int:
    """Return the index of the most likely header row (0 if unsure)."""
    if not grid:
        return 0
    best_i, best = 0, float("-inf")
    limit = min(max_scan, len(grid) - 1) if len(grid) > 1 else 1
    for i in range(max(limit, 1)):
        hl = _header_likeness(grid[i])
        if hl < 0:
            continue
        dl = _data_likeness(grid, i + 1)
        if dl < 0:              # nothing below → not a header
            continue
        score = hl + 0.8 * dl
        if score > best:
            best_i, best = i, score
    return best_i


def build_columns(header_row) -> List[str]:
    """Turn a header row into clean, de-duplicated column names."""
    names, seen = [], {}
    for i, cell in enumerate(header_row):
        name = cell_str(cell) or f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        names.append(name)
    return names
