"""Quality-check an extracted financial table by re-deriving its subtotals.

You can't guarantee a rule-based extractor is perfect on an arbitrary PDF, but
you can check whether the numbers it pulled are internally consistent: does
Gross Profit = Revenue - Cost of Sales? Does Profit for the period = Profit
before taxation - Taxation? When those chains foot, the table is very likely
extracted correctly; when they don't, it's a signal to look.

Returns {checked, passed, status} where status is 'ok', 'check', or 'n/a'.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..models.money import parse_decimal

# target line item  <-  (sum of these)  -  (sum of these)
_CHAINS = [
    ("grossprofit", ["revenue"], ["costofsales"]),
    ("ebitda", ["grossprofit"], ["operatingexpenses"]),
    ("operatingprofitebit", ["ebitda"], ["depreciationamortisation"]),
    ("profitbeforetax", ["operatingprofitebit"], ["netfinancecosts"]),
    ("netprofitaftertax", ["profitbeforetax"], ["incometaxexpense"]),
    ("profitfortheperiod", ["profitbeforetaxation"], ["taxation"]),
    ("operatingprofitbeforeimpairmentandtaxation", ["operatingincome"],
     ["operatingexpenses"]),
]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _num(v: Any):
    d = parse_decimal(v)
    return float(d) if d is not None else None


def reconcile_subtotals(columns: List[str], rows: List[Dict[str, Any]]) -> Dict:
    label_col = columns[0]
    value_cols = columns[1:]
    idx = {_norm(r.get(label_col, "")): [_num(r.get(c)) for c in value_cols]
           for r in rows}
    checked = passed = 0
    failures: List[str] = []
    for target, adds, subs in _CHAINS:
        if target not in idx or any(k not in idx for k in adds + subs):
            continue
        for col in range(len(value_cols)):
            tv = idx[target][col]
            if tv is None:
                continue
            comps = [idx[k][col] for k in adds + subs]
            if any(x is None for x in comps):
                continue
            # Financial statements print costs as negatives already, so the
            # subtotal is the signed sum of its components. If a "subtracted"
            # component was printed positive, subtracting also works — so accept
            # either reading.
            signed_sum = sum(idx[a][col] for a in adds) + sum(idx[b][col] for b in subs)
            subtract = sum(idx[a][col] for a in adds) - sum(idx[b][col] for b in subs)
            checked += 1
            if min(abs(signed_sum - tv), abs(subtract - tv)) <= 1.0:
                passed += 1
            else:
                failures.append(f"{target}[{value_cols[col]}]: got {tv:g}, "
                                f"expected {signed_sum:g}")
    status = "n/a" if checked == 0 else ("ok" if passed == checked else "check")
    return {"checked": checked, "passed": passed, "status": status,
            "failures": failures[:5]}
