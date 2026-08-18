"""Reconstruct financial tables from a PDF page using word geometry.

Generic table detection fails on bank/statement PDFs: the tables are ruled by
alignment, not borders, headers span multiple lines, the first column is an
unlabelled row-label ("key"), and footnote superscripts sit between columns.

This extractor instead:
  * clusters words into lines by their vertical position;
  * finds the value columns by clustering the right edges of numeric words that
    repeat down the page (so a stray "1" in "Common Equity Tier 1" is ignored);
  * treats everything left of the first value column as the row label (key);
  * merges multi-line period headers into clean column names;
  * drops footnote superscripts by font size.

Output is a clean grid: [label, col1, col2, ...] with one row per line item —
exactly the key/value shape reconciliation needs.
"""
from __future__ import annotations

import re
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

# a token that is a financial value: 1,234 / (1,234.5) / 12.3 / 45% / (7)bps / nm / -
_NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?(%|bps)?$")
_PLACEHOLDER = {"-", "–", "—", "nm", "n/a"}
_UNIT = re.compile(r"^\$?m?illion$|^\$m$|^%$|^\$million$", re.I)


def _is_value(text: str) -> bool:
    t = text.strip()
    return t.lower() in _PLACEHOLDER or bool(_NUM.match(t))


def _cluster_lines(words: List[dict], tol: float = 3.0) -> List[List[dict]]:
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda x: (round(x["top"] / tol), x["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    for ln in lines:
        ln.sort(key=lambda x: x["x0"])
    return lines


def _cluster_columns(words: List[dict], page_width: float, n_rows: int
                     ) -> List[Tuple[float, float]]:
    """Cluster right-edges (x1) of numeric words into value columns."""
    nums = sorted((w for w in words if _is_value(w["text"])), key=lambda x: x["x1"])
    if not nums:
        return []
    clusters: List[List[dict]] = [[nums[0]]]
    for w in nums[1:]:
        if w["x1"] - clusters[-1][-1]["x1"] <= 16:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    cols: List[Tuple[float, float]] = []
    min_members = max(2, int(0.35 * n_rows))
    for c in clusters:
        mean_x1 = sum(w["x1"] for w in c) / len(c)
        if len(c) >= min_members and mean_x1 > 0.25 * page_width:
            x0 = min(w["x0"] for w in c)
            x1 = max(w["x1"] for w in c)
            cols.append((x0, x1))
    return cols


def _assign(line: List[dict], cols: List[Tuple[float, float]], median_size: float
            ) -> Tuple[str, List[str], bool]:
    """Split a line into (label, [values per column], has_any_value)."""
    first_col_left = cols[0][0]
    label_words, col_words = [], {i: [] for i in range(len(cols))}
    for w in line:
        cx = (w["x0"] + w["x1"]) / 2
        placed = False
        for i, (x0, x1) in enumerate(cols):
            if x0 - 12 <= cx <= x1 + 12:
                col_words[i].append(w)
                placed = True
                break
        if not placed and w["x1"] < first_col_left - 4:
            # drop footnote superscripts: tiny numeric words in the label gap
            if _is_value(w["text"]) and w.get("size", median_size) < median_size - 1.2:
                continue
            label_words.append(w)
    values, any_val = [], False
    for i in range(len(cols)):
        cell = " ".join(w["text"] for w in sorted(col_words[i], key=lambda x: x["x0"]))
        cell = cell.strip()
        if cell:
            any_val = True
        values.append(cell)
    label = " ".join(w["text"] for w in label_words).strip()
    label = re.sub(r"\s+", " ", label)
    return label, values, any_val


def _clean_header(s: str) -> str:
    s = re.sub(r"[\u00b9\u00b2\u00b3\u2070-\u2079]", "", s)   # superscripts
    s = re.sub(r"\s+\d{1,2}$", "", s)                         # trailing footnote marker
    return re.sub(r"\s+", " ", s).strip()


def _mostly_text(cells: List[str]) -> bool:
    filled = [c for c in cells if c]
    if not filled:
        return False
    texty = sum(1 for c in filled if not _is_value(c.split()[0])) if filled else 0
    return texty >= max(1, len(filled) / 2)


_YEARISH = re.compile(r"^((19|20)\d{2}[A-Za-z]?|[Qq][1-4]'?\d{0,4}|FY'?\d{2,4}|H[12]'?\d{0,4})$")


def _is_period_row(label: str, values: List[str]) -> bool:
    """A sub-header row: no row label, and every cell is a year/period token."""
    filled = [v for v in values if v]
    if len(filled) < 2 or not all(_YEARISH.match(v.replace(" ", "")) for v in filled):
        return False
    # the label cell may hold a unit caption ("USDm", "ZAR millions", "$m")
    return (not label) or (len(label.split()) <= 3 and not re.search(r"\d", label))


def _header_names_from(header_lines: List[List[dict]],
                       cols: List[Tuple[float, float]]) -> List[str]:
    per_col: List[List[str]] = [[] for _ in cols]
    for ln in header_lines:
        words = [w for w in sorted(ln, key=lambda x: x["x0"])
                 if not _UNIT.match(w["text"])
                 and (not _is_value(w["text"]) or _YEARISH.match(w["text"].strip()))]
        if not words:
            continue
        # direct hits: a word whose centre sits inside the column band
        hits: List[List[str]] = [[] for _ in cols]
        for w in words:
            cx = (w["x0"] + w["x1"]) / 2
            for i, (x0, x1) in enumerate(cols):
                if x0 - 16 <= cx <= x1 + 16:
                    hits[i].append(w["text"])
        # spanning tier (e.g. "Actual" over 2 cols, "Baseline" over 4): spread
        # only words that already claimed a column, so left-margin headings and
        # section titles never leak into column names.
        claimed = [w for w in words
                   if any(x0 - 16 <= (w["x0"] + w["x1"]) / 2 <= x1 + 16
                          for x0, x1 in cols)]
        if claimed and len(claimed) < len(cols):
            for i, (x0, x1) in enumerate(cols):
                if hits[i]:
                    continue
                mid = (x0 + x1) / 2
                nearest = min(claimed, key=lambda w: abs((w["x0"] + w["x1"]) / 2 - mid))
                hits[i].append(nearest["text"])
        for i, texts in enumerate(hits):
            if texts:
                per_col[i].append(" ".join(texts))

    names = [_clean_header(" ".join(parts)) for parts in per_col]
    seen: Dict[str, int] = {}
    out = []
    for n in names:
        n = n or "value"
        if n in seen:
            seen[n] += 1; out.append(f"{n} ({seen[n]})")
        else:
            seen[n] = 0; out.append(n)
    return out


def _find_title(lines: List[List[dict]], block_top: float, page_width: float,
                median_size: float, skip_tops=None) -> Optional[str]:
    """Nearest heading above a table block (short, larger/bold, non-tabular)."""
    skip = skip_tops or set()
    best, best_score = None, 0.0
    for ln in lines:
        top = ln[0]["top"]
        if round(top) in skip:
            continue
        if top >= block_top - 1 or block_top - top > 95:
            continue
        if any(_is_value(w["text"]) and (w["x0"] + w["x1"]) / 2 > 0.4 * page_width
               for w in ln):
            continue
        text = " ".join(w["text"] for w in sorted(ln, key=lambda x: x["x0"])).strip()
        if not text or len(text.split()) > 9:
            continue
        size = max(w.get("size", median_size) for w in ln)
        bold = any("bold" in str(w.get("fontname", "")).lower() for w in ln)
        if size <= median_size * 1.05 and not bold:
            continue
        score = size + (2 if bold else 0) - (block_top - top) * 0.02
        if score > best_score:
            best, best_score = text, score
    return re.sub(r"\s+continued$", "", best).strip() if best else None


def _breaks_schema(label: str, values: List[str]) -> bool:
    """True if a row breaks a financial table's numeric schema.

    Data rows carry mostly numbers in the value columns. Footnotes and the
    commentary that follows a table are prose: a long sentence label and value
    cells that are words, not numbers. That is the signal the table has ended.
    """
    filled = [v for v in values if v]
    if not filled:
        return False
    numeric = sum(1 for v in filled if _is_value(v))
    prose_cells = numeric == 0                       # no value cell is a number
    long_label = len(label.split()) >= 6             # a sentence, not a line item
    return prose_cells and long_label


def _is_wrap_of(prev_row: Dict[str, str], col_names: List[str],
                values: List[str]) -> bool:
    """True if `values` are the tail of numbers that wrapped from `prev_row`.

    A PDF may break "-15,280" across two lines, leaving "-" on the first and
    "15,280" on the second. The continuation has no row label and only fills
    columns whose previous cell is a bare sign or empty.
    """
    filled = [(n, v) for n, v in zip(col_names, values) if v]
    if not filled:
        return False
    for name, _v in filled:
        prev = (prev_row.get(name) or "").strip()
        if prev not in ("-", "\u2013", "\u2014", "+", ""):
            return False
    return True


_VOWELS = set("aeiouAEIOU")


def _is_garble_token(tok: str) -> bool:
    """A single word that looks like OCR junk: 8+ letters, almost no vowels."""
    core = re.sub(r"[^A-Za-z]", "", tok)
    if len(core) < 8:
        return False
    return sum(c in _VOWELS for c in core) / len(core) < 0.12


def _strip_garble(label: str) -> str:
    """Drop OCR-junk tokens from a label, keeping the real words.

    e.g. "Operating Profit (EBIT) hjdksdkshkdhskdhkhkhh skdhkshdhkhkshd"
      -> "Operating Profit (EBIT)". Never empties a label: if every token looks
    garbled (a genuinely non-Latin label), the original is kept unchanged.
    """
    toks = label.split()
    kept = [t for t in toks if not _is_garble_token(t)]
    out = " ".join(kept).strip()
    return out or label


_CONJ_END = {"and", "of", "to", "for", "with", "the", "a", "an", "in", "on", "or"}


def _incomplete_label(s: str) -> bool:
    """A label that grammatically continues onto the next line.

    Financial line items don't end with '&' or a dangling conjunction, and if a
    bracket is opened it stays open until it closes. Any of those means the
    label is unfinished and the next line completes it.
    """
    s = (s or "").strip()
    if not s:
        return False
    if s.endswith("&"):
        return True
    if s.count("(") > s.count(")"):
        return True
    last = s.split()[-1].lower().rstrip(",")
    return last in _CONJ_END


def _continuation_start(s: str) -> bool:
    """A line that grammatically continues the row above: it starts lowercase,
    opens a qualifier bracket ("(incl ...)"), or closes one. A genuine new line
    item almost always starts with a capital letter."""
    s = (s or "").strip()
    if not s:
        return False
    return s[0].islower() or s[0] in "()[]"


def _looks_like_section(label: str) -> bool:
    """A value-less line that reads as a section sub-header rather than a
    wrapped fragment of the row above.

    Sub-headers are short titles that start with a capital letter and are not
    lowercase continuation words ("Amortisation", "and joint ventures"). This
    is a soft signal; the caller also uses line spacing.
    """
    s = label.strip()
    if not s or len(s.split()) > 6:
        return False
    first = s.split()[0]
    return first[:1].isupper() and first.lower() not in _CONT_WORDS


_CONT_WORDS = {"and", "or", "of", "the", "to", "in", "for", "with", "on",
               "amortisation", "shareholders", "ventures", "taxation"}


def extract_financial_tables(page, label_header: str = "Line item"
                             ) -> List[Dict[str, Any]]:
    """Return a list of clean tables: {name, title, columns, rows(list[dict])}."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False,
                               extra_attrs=["size", "fontname"])
    if not words:
        return []
    lines = _cluster_lines(words)

    def _is_tabular_line(ln):
        return any(_is_value(w["text"]) and (w["x0"] + w["x1"]) / 2 > 0.25 * page.width
                   for w in ln)

    # Base the body font size on the table rows themselves, not the whole page:
    # a footnote-heavy page has many tiny words that would drag a global median
    # down and make real rows look like "headings".
    body_sizes = [w.get("size", 10) for ln in lines if _is_tabular_line(ln)
                  for w in ln]
    median_size = median(body_sizes) if body_sizes else (
        median([w.get("size", 10) for w in words]) or 10)

    def is_tabular(ln):
        return any(_is_value(w["text"]) and (w["x0"] + w["x1"]) / 2 > 0.25 * page.width
                   for w in ln)

    tops = sorted({round(l[0]["top"]) for l in lines})
    diffs = [b - a for a, b in zip(tops, tops[1:]) if b > a]
    line_gap = median(diffs) if diffs else 14.0

    def is_label_wrap(ln, prev_top, first_col_x=None):
        """A value-less left-region line that stays in the table: a wrapped
        continuation of the row above, or a section sub-header. The label region
        is bounded by the first value column (long section titles can run well
        past a fixed fraction of the page). Footnotes (smaller type) and
        headings (larger type) are excluded."""
        bound = first_col_x if first_col_x is not None else 0.40 * page.width
        if any((w["x0"] + w["x1"]) / 2 >= bound for w in ln):
            return False
        size = max(w.get("size", median_size) for w in ln)
        if size > median_size * 1.05:
            return False          # a heading
        if size < median_size * 0.95:
            return False          # footnote / small print, not a table cell
        return (ln[0]["top"] - prev_top) <= line_gap * 1.6

    # left edge of the first value column across the page — bounds the label zone
    _page_cols = _cluster_columns(words, page.width, len(lines))
    _first_col_x = _page_cols[0][0] if _page_cols else 0.40 * page.width

    blocks: List[List[List[dict]]] = []
    cur: List[List[dict]] = []
    gap = 0
    prev_top = None
    for idx, ln in enumerate(lines):
        if is_tabular(ln):
            if not cur and idx > 0 and _page_cols:
                # a section sub-header sitting just above the first data row
                # (e.g. "Financial performance") belongs to this table
                prev_ln = lines[idx - 1]
                plabel, pvals, pany = _assign(prev_ln, _page_cols, median_size)
                if (not pany and plabel and _looks_like_section(plabel)
                        and (ln[0]["top"] - prev_ln[0]["top"]) <= line_gap * 1.6
                        and max(w.get("size", median_size) for w in prev_ln)
                        <= median_size * 1.05):
                    cur.append(prev_ln)
            cur.append(ln); gap = 0; prev_top = ln[0]["top"]
        elif cur and prev_top is not None and is_label_wrap(ln, prev_top, _first_col_x):
            cur.append(ln); gap = 0; prev_top = ln[0]["top"]
        else:
            gap += 1
            if cur and gap > 1:
                blocks.append(cur); cur = []; prev_top = None
    if cur:
        blocks.append(cur)


    tables = []
    for b_idx, block in enumerate(blocks):
        block_words = [w for ln in block for w in ln]
        cols = _cluster_columns(block_words, page.width, len(block))
        if not cols:
            continue

        # split leading header-like lines (period labels) from data rows
        assigned = [(ln, _assign(ln, cols, median_size)) for ln in block]
        data_start = 0
        for ln, (label, values, _any) in assigned:
            if (_mostly_text(values) and not label) or _is_period_row(label, values):
                data_start += 1
            else:
                break
        header_in_block = [ln for ln, _ in assigned[:data_start]]
        # climb upward for header lines; stop at a big gap or a prose line
        btop = block[0][0]["top"]
        above: List[List[dict]] = []
        for ln in reversed([l for l in lines if l[0]["top"] < btop - 1]):
            if btop - ln[0]["top"] > 62:
                break
            aligned = sum(1 for w in ln if any(x0 - 16 <= (w["x0"] + w["x1"]) / 2 <= x1 + 16
                                               for x0, x1 in cols))
            if len(ln) > 8 and aligned < len(ln) / 2:
                break  # reached a paragraph / section title
            above.append(ln)
        above = [] if header_in_block else list(reversed(above))[-4:]
        header_lines = above + header_in_block
        col_names = _header_names_from(header_lines, cols)
        columns = [label_header] + col_names
        # a line only counts as "header" (and so is barred from being the title)
        # if it actually sits over the value columns
        header_tops = {round(l[0]["top"]) for l in header_lines
                       if any(x0 - 16 <= (w["x0"] + w["x1"]) / 2 <= x1 + 16
                              for w in l for x0, x1 in cols)}

        rows: List[Dict[str, str]] = []
        prev_data_top = None
        pending_head = ""          # a label whose values are on a later line
        seq = assigned[data_start:]
        for i, (ln, (label, values, any_val)) in enumerate(seq):
            if not label and not any_val:
                continue
            if re.fullmatch(r"\d{1,3}", label) and not any_val:
                continue  # page-number / stray footer
            if rows and not label and any_val and _is_wrap_of(rows[-1], col_names, values):
                prev = rows[-1]
                for name, val in zip(col_names, values):
                    if val:
                        prev[name] = (prev.get(name) or "") + val
                continue
            # schema break: once we have numeric data rows, a row whose value
            # cells are prose (footnotes, commentary that follows the table) is
            # NOT part of the table — stop here and drop the rest of the block.
            if rows and not pending_head and _breaks_schema(label, values):
                break
            if not any_val and label:
                nxt = seq[i + 1] if i + 1 < len(seq) else None
                nxt_label, _nvals, nxt_any = (nxt[1] if nxt else ("", [], False))
                next_is_data = bool(nxt_any)
                # if the NEXT line is a continuation (lowercase / "("), then THIS
                # value-less line is the head of that row — merge them.
                next_is_continuation = next_is_data and _continuation_start(nxt_label)
                prev_incomplete = bool(rows) and _incomplete_label(rows[-1][label_header])
                if pending_head:
                    pending_head = f"{pending_head} {label}".strip()
                elif next_is_continuation or _incomplete_label(label):
                    # a label head whose numbers are on the following line
                    pending_head = label
                elif _looks_like_section(label) and next_is_data:
                    # a genuine section sub-header (next line is a NEW item)
                    rows.append({label_header: label,
                                 **{name: "" for name in col_names}})
                    prev_data_top = ln[0]["top"]
                elif rows and (_continuation_start(label) or prev_incomplete):
                    # a wrapped tail of the row above
                    rows[-1][label_header] = f"{rows[-1][label_header]} {label}".strip()
                else:
                    pending_head = label
                continue
            # a data row (has values) — prepend any pending label head
            full = f"{pending_head} {label}".strip() if pending_head else label
            pending_head = ""
            row = {label_header: full}
            for name, val in zip(col_names, values):
                row[name] = val
            rows.append(row)
            prev_data_top = ln[0]["top"]

        if not rows:
            continue
        for r in rows:                       # drop OCR-junk tokens from labels
            r[label_header] = _strip_garble(r[label_header])
        # reject prose blocks (sentences with inline numbers) vs real tables
        avg_label_words = sum(len(r[label_header].split()) for r in rows) / len(rows)
        cells = [v for r in rows for k, v in r.items() if k != label_header]
        density = (sum(1 for c in cells if c) / len(cells)) if cells else 0
        if avg_label_words > 7:
            continue
        if len(cols) >= 2 and density < 0.45:
            continue
        if len(cols) == 1 and (len(rows) < 4 or avg_label_words > 5):
            continue
        title = _find_title(lines, block[0][0]["top"], page.width, median_size,
                            skip_tops=header_tops)
        tables.append({"name": f"table_{b_idx + 1}", "title": title,
                       "columns": columns, "rows": rows})
    return tables
