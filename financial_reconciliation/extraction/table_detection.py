"""Split a grid into one or more table regions and materialize FinancialTables.

A single sheet may hold several stacked/side-by-side tables separated by blank
rows or columns; each region gets its own header detection.
"""
from __future__ import annotations

from typing import List

from ..models.documents import FinancialRecord, FinancialTable
from .grids import Grid, is_number, normalize_grid, row_is_empty, trim
from .header_detection import build_columns, detect_header_row


def _header_band(region: Grid, h: int) -> int:
    """Return the last row index of a multi-tier header starting at `h`.

    A sub-header row (e.g. the year row under merged 'Baseline') has an empty
    first cell — the row-label column — but content in the value columns.
    """
    last = h
    for i in range(h + 1, min(h + 4, len(region) - 1)):
        row = region[i]
        first_empty = row[0] is None or str(row[0]).strip() == ""
        others = [c for c in row[1:] if not (c is None or str(c).strip() == "")]
        if first_empty and len(others) >= 2:
            last = i
        else:
            break
    return last


def _join_headers(region: Grid, h0: int, h1: int) -> List[str]:
    """Combine header-band rows into one label per column."""
    if h1 <= h0:
        return build_columns(region[h0])
    width = max(len(region[r]) for r in range(h0, h1 + 1))
    names = []
    for c in range(width):
        parts, seen = [], set()
        for r in range(h0, h1 + 1):
            row = region[r]
            val = row[c] if c < len(row) else None
            if val is None:
                continue
            s = str(val).strip()
            if isinstance(val, float) and val.is_integer():
                s = str(int(val))
            if s and s not in seen:
                seen.add(s); parts.append(s)
        names.append(" ".join(parts))
    return build_columns(names)


def _split_rows(grid: Grid) -> List[Grid]:
    """Split on runs of fully-empty rows, then re-join continuation blocks.

    A blank row inside a statement (e.g. before 'EBITDA') must NOT start a new
    table: the rows below follow the same pattern and have no header of their
    own. We therefore only keep a split when the next block actually begins
    with a header-like row.
    """
    blocks, cur = [], []
    for row in grid:
        if row_is_empty(row):
            if cur:
                blocks.append(cur); cur = []
        else:
            cur.append(row)
    if cur:
        blocks.append(cur)
    if len(blocks) <= 1:
        return blocks

    merged = [blocks[0]]
    for b in blocks[1:]:
        if _starts_new_table(b):
            merged.append(b)
        else:
            merged[-1] = merged[-1] + b      # continuation of the same table
    return merged


def _starts_new_table(block: Grid) -> bool:
    """True if this block opens with its own header row."""
    if not block:
        return False
    first = block[0]
    cells = [c for c in first if not (c is None or str(c).strip() == "")]
    if len(cells) < 2:
        return False
    numeric = sum(1 for c in cells if is_number(c))
    # a header row is mostly text; a continuation row carries numbers
    return (numeric / len(cells)) < 0.34


def _split_cols(block: Grid) -> List[Grid]:
    """Split a row-block on fully-empty columns (side-by-side tables)."""
    block = normalize_grid(block)
    width = len(block[0]) if block else 0
    empty = [all((c is None or str(c).strip() == "") for c in (r[j] for r in block))
             for j in range(width)]
    groups, cur = [], []
    for j in range(width):
        if empty[j]:
            if cur:
                groups.append(cur); cur = []
        else:
            cur.append(j)
    if cur:
        groups.append(cur)
    if len(groups) <= 1:
        return [block]
    return [[[r[j] for j in g] for r in block] for g in groups]


def find_table_regions(grid: Grid, min_rows: int = 2, min_cols: int = 2) -> List[Grid]:
    """Return trimmed sub-grids, each a candidate table."""
    regions: List[Grid] = []
    for row_block in _split_rows(grid):
        for region in _split_cols(row_block):
            t = trim(region)
            if len(t) >= min_rows and (len(t[0]) if t else 0) >= min_cols:
                regions.append(t)
    return regions


def region_to_table(region: Grid, source_file: str, table_name: str) -> FinancialTable:
    h = detect_header_row(region)
    h_end = _header_band(region, h)
    columns = _join_headers(region, h, h_end)
    records: List[FinancialRecord] = []
    for idx, row in enumerate(region[h_end + 1:]):
        row = list(row) + [None] * (len(columns) - len(row))
        values = {columns[j]: row[j] for j in range(len(columns))}
        records.append(FinancialRecord(values=values, source_file=source_file,
                                       table_name=table_name, row_index=idx))
    return FinancialTable(name=table_name, columns=columns,
                          records=records, source_file=source_file)


def tables_from_grid(grid: Grid, source_file: str, base_name: str) -> List[FinancialTable]:
    """Full pipeline: grid -> regions -> tables (multi-table aware)."""
    regions = find_table_regions(grid)
    if not regions:
        return []
    if len(regions) == 1:
        return [region_to_table(regions[0], source_file, base_name)]
    return [region_to_table(r, source_file, f"{base_name}#{i + 1}")
            for i, r in enumerate(regions)]
