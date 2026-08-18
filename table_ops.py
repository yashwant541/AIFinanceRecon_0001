"""Pure table-editing operations used by the View → Edit mode.

Every function takes and returns a plain {columns, rows} table (rows are lists,
aligned to columns) so the frontend, the backend and the reference library all
speak the same shape. None of these mutate their input.
"""
from __future__ import annotations

from typing import Any, Dict, List

Table = Dict[str, Any]   # {"columns": [...], "rows": [[...], ...]}


def _clean(name: str, used: set) -> str:
    name = (str(name).strip() or "column")
    base, n = name, 1
    while name in used:
        n += 1
        name = f"{base} ({n})"
    used.add(name)
    return name


def promote_header(table: Table, row_index: int) -> Table:
    """Make row `row_index` the column header; drop it and the rows above it."""
    rows = table["rows"]
    if not (0 <= row_index < len(rows)):
        return {"columns": list(table["columns"]), "rows": [list(r) for r in rows]}
    header, used = [], set()
    for cell in rows[row_index]:
        header.append(_clean("" if cell is None else str(cell), used))
    return {"columns": header, "rows": [list(r) for r in rows[row_index + 1:]]}


def delete_rows(table: Table, indices: List[int]) -> Table:
    drop = set(indices)
    rows = [list(r) for i, r in enumerate(table["rows"]) if i not in drop]
    return {"columns": list(table["columns"]), "rows": rows}


def rename_columns(table: Table, names: List[str]) -> Table:
    used, cols = set(), []
    for i, orig in enumerate(table["columns"]):
        new = names[i] if i < len(names) and str(names[i]).strip() else orig
        cols.append(_clean(str(new), used))
    return {"columns": cols, "rows": [list(r) for r in table["rows"]]}


def edit_label(table: Table, row_index: int, text: str) -> Table:
    """Edit the first-column (label) text of a single row; values untouched."""
    rows = [list(r) for r in table["rows"]]
    if 0 <= row_index < len(rows) and rows[row_index]:
        rows[row_index][0] = text
    return {"columns": list(table["columns"]), "rows": rows}


def is_complex(table: Table) -> bool:
    """A table worth pivoting: 2+ value columns (a wide matrix). A single value
    column is already long/tidy and can't be simplified further."""
    return len(table["columns"]) >= 3


def pivot_long(table: Table, id_label: str = "Line item",
               period_name: str = "Period", value_name: str = "Value") -> Table:
    """Melt a wide matrix into tidy long form: [id cols…, Period, Value]."""
    from .reshape import melt
    columns = list(table["columns"])
    row_dicts = [{columns[i]: (r[i] if i < len(r) else None)
                  for i in range(len(columns))} for r in table["rows"]]
    long_cols, long_rows = melt(columns, row_dicts, period_name, value_name)
    rows = [[lr.get(c) for c in long_cols] for lr in long_rows]
    return {"columns": long_cols, "rows": rows}


def apply_ops(table: Table, ops: List[Dict[str, Any]]) -> Table:
    """Apply a sequence of edit operations in order."""
    t = {"columns": list(table["columns"]), "rows": [list(r) for r in table["rows"]]}
    for op in ops:
        kind = op.get("op")
        if kind == "promote_header":
            t = promote_header(t, int(op["row"]))
        elif kind == "delete_rows":
            t = delete_rows(t, [int(i) for i in op.get("rows", [])])
        elif kind == "rename_columns":
            t = rename_columns(t, list(op.get("names", [])))
        elif kind == "edit_label":
            t = edit_label(t, int(op["row"]), str(op.get("text", "")))
        elif kind == "pivot_long":
            t = pivot_long(t)
    return t
