"""Selectable PDF table-extraction engines.

Different engines have different strengths:

  * "native"  – our coordinate-clustering extractor. Best at header/column
                naming, multi-tier headers, section sub-headers and cleaning.
                Occasionally misses a table region on an unusual layout.
  * "camelot" – Camelot (flavor='stream'). Strong at locating borderless table
                *regions* and aligning column bodies, but weak at naming
                headers/columns. Requires the camelot-py package (Ghostscript
                is used by the 'lattice' flavor; 'stream' generally does not).
  * "camelot+native" – best of both: Camelot finds the grid, then our own
                header detection + cleaning pipeline names and tidies it.

The webapp exposes this as a per-upload choice; "native" is the default so
nothing changes unless a user opts in.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List

try:
    import camelot
    HAVE_CAMELOT = True
except Exception:  # noqa: BLE001
    HAVE_CAMELOT = False


ENGINES = ["native", "camelot", "camelot+native"]


def available_engines() -> List[str]:
    """Engines usable in this environment (camelot dropped if not installed)."""
    return [e for e in ENGINES if e == "native" or HAVE_CAMELOT]


# --------------------------------------------------------------------------- #
#  camelot -> our grid/table pipeline
# --------------------------------------------------------------------------- #
def _camelot_grids(data: bytes, pages: str = "all") -> List[Dict[str, Any]]:
    """Return raw Camelot tables as {page, grid(list[list[str]])}."""
    if not HAVE_CAMELOT:
        return []
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            tables = camelot.read_pdf(tmp.name, pages=pages, flavor="stream",
                                      edge_tol=500)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for i in range(tables.n):
            df = tables[i].df
            grid = [[("" if c is None else str(c)) for c in row]
                    for row in df.values.tolist()]
            out.append({"page": int(tables[i].page), "grid": grid})
        return out


def _grid_to_tables(grid, filename, name):
    """Run our header-detection + cleaning on a raw grid (shared with Excel)."""
    from .table_detection import tables_from_grid
    return tables_from_grid(grid, filename, name)


def extract_with_engine(filename: str, data: bytes, engine: str,
                        native_parse, pages_filter=None):
    """Dispatch to the chosen engine.

    `native_parse` is a callable(filename, data, pages) -> ExtractionResult so
    this module doesn't import the parser (avoids a cycle). Returns a list of
    FinancialTable.
    """
    engine = engine if engine in available_engines() else "native"

    if engine == "native":
        return native_parse(filename, data, pages_filter).document.tables

    grids = _camelot_grids(data)
    if pages_filter:
        want = set(pages_filter)
        grids = [g for g in grids if g["page"] in want]

    if not grids:                      # camelot found nothing -> fall back
        return native_parse(filename, data, pages_filter).document.tables

    tables = []
    if engine == "camelot":
        # camelot's own grid, lightly cleaned by our shared grid pipeline
        for gi, g in enumerate(grids):
            for t in _grid_to_tables(g["grid"], filename,
                                     f"page{g['page']}_camelot{gi + 1}"):
                tables.append(t)
    elif engine == "camelot+native":
        # camelot finds the region; our detector names headers & cleans it
        for gi, g in enumerate(grids):
            for t in _grid_to_tables(g["grid"], filename,
                                     f"page{g['page']}_table{gi + 1}"):
                tables.append(t)
    return tables or native_parse(filename, data, pages_filter).document.tables
