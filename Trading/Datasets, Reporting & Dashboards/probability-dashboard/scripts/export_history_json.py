#!/usr/bin/env python3
"""
export_history_json.py
----------------------
Reads the processed daily OHLC CSVs (same source as generate_stats.py)
and exports recent history to:
  data/stats/NQ_history.json
  data/stats/ES_history.json

- Daily:   last 10 sessions (newest first)
- Weekly:  last 4 weeks aggregated from daily (newest first)
- Monthly: last 3 months aggregated from daily (newest first)

Run as part of the weekly update workflow.
"""

import json
from pathlib import Path
from collections import defaultdict

PROCESSED_DIR = Path("/Users/shawnjudge/Library/Mobile Documents/iCloud~md~obsidian/Documents/SJ Work Vault/04 - reporting-dashboards/probability-dashboard/v1/data/processed")
OUT_DIR = Path(__file__).parent.parent / "data" / "stats"

DAILY_ROWS   = 10
WEEKLY_ROWS  = 4
MONTHLY_ROWS = 3

INSTRUMENT_MAP = {
    "NQ": "MNQ",   # NQ_history.json ← MNQ_daily_ohlc.csv
    "ES": "MES",   # ES_history.json ← MES_daily_ohlc.csv
}


def read_ohlc_csv(instrument):
    """Read MNQ_daily_ohlc.csv or MES_daily_ohlc.csv, return list of dicts oldest→newest."""
    path = PROCESSED_DIR / f"{instrument}_daily_ohlc.csv"
    if not path.exists():
        print(f"  [WARN] not found: {path}")
        return []
    rows = []
    with open(path) as f:
        headers = [h.strip() for h in f.readline().split(",")]
        for line in f:
            vals = line.strip().split(",")
            rows.append(dict(zip(headers, vals)))
    return rows


def r(v, dec=2):
    try: return round(float(v), dec)
    except: return ""


def build_daily(rows, n=DAILY_ROWS):
    """Last n sessions, newest first."""
    recent = [row for row in rows if row.get("date") and row.get("close")][-n:]
    out = []
    for row in reversed(recent):
        out.append({
            "date":       row["date"],
            "open":       r(row["open"]),
            "high":       r(row["high"]),
            "low":        r(row["low"]),
            "close":      r(row["close"]),
            "volume":     row.get("volume", ""),
            "range":      r(row.get("daily_range", "")),
            "direction":  "UP" if r(row.get("daily_change", 0)) >= 0 else "DOWN",
            "change_pct": r(row.get("daily_change_pct", ""), 3),
        })
    return out


def build_weekly(rows, n=WEEKLY_ROWS):
    """Aggregate daily → weekly bars, last n weeks, newest first."""
    from datetime import datetime, timedelta
    weeks = defaultdict(list)
    for row in rows:
        try:
            d = datetime.strptime(row["date"], "%Y-%m-%d")
            # Monday of that week
            monday = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
            weeks[monday].append(row)
        except: pass

    result = []
    sorted_weeks = sorted(weeks.keys())
    prev_close = None
    for wk in sorted_weeks:
        bars = weeks[wk]
        try:
            o = r(bars[0]["open"])
            h = r(max(float(b["high"]) for b in bars))
            l = r(min(float(b["low"])  for b in bars))
            c = r(bars[-1]["close"])
            rng = r(h - l)
            chg = r((c - prev_close) / prev_close * 100, 3) if prev_close else ""
            direction = ("UP" if isinstance(chg, float) and chg >= 0 else "DOWN") if chg != "" else ""
            result.append({"date": wk, "open": o, "high": h, "low": l, "close": c,
                           "range": rng, "direction": direction, "change_pct": chg})
            prev_close = c
        except: pass

    return list(reversed(result[-n:]))


def build_monthly(rows, n=MONTHLY_ROWS):
    """Aggregate daily → monthly bars, last n months, newest first."""
    months = defaultdict(list)
    for row in rows:
        if row.get("date") and len(row["date"]) >= 7:
            months[row["date"][:7]].append(row)

    result = []
    sorted_months = sorted(months.keys())
    prev_close = None
    for mk in sorted_months:
        bars = months[mk]
        try:
            o = r(bars[0]["open"])
            h = r(max(float(b["high"]) for b in bars))
            l = r(min(float(b["low"])  for b in bars))
            c = r(bars[-1]["close"])
            rng = r(h - l)
            chg = r((c - prev_close) / prev_close * 100, 3) if prev_close else ""
            direction = ("UP" if isinstance(chg, float) and chg >= 0 else "DOWN") if chg != "" else ""
            result.append({"date": mk, "open": o, "high": h, "low": l, "close": c,
                           "range": rng, "direction": direction, "change_pct": chg})
            prev_close = c
        except: pass

    return list(reversed(result[-n:]))


def export_instrument(prefix, instrument, out_file):
    print(f"  Reading {instrument}_daily_ohlc.csv...")
    rows = read_ohlc_csv(instrument)
    if not rows:
        return

    daily   = build_daily(rows)
    weekly  = build_weekly(rows)
    monthly = build_monthly(rows)

    payload = {"daily": daily, "weekly": weekly, "monthly": monthly}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"    → {len(daily)} daily  | {len(weekly)} weekly  | {len(monthly)} monthly")
    print(f"    Daily:   {[r['date'] for r in daily[:3]]}...")
    print(f"    Monthly: {[r['date'] for r in monthly]}")


def main():
    print(f"Source: {PROCESSED_DIR}\n")
    for prefix, instrument in INSTRUMENT_MAP.items():
        export_instrument(prefix, instrument, OUT_DIR / f"{prefix}_history.json")
    print("\nDone.")


if __name__ == "__main__":
    main()

