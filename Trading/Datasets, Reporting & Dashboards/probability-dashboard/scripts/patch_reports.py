#!/usr/bin/env python3
"""
patch_reports.py — Adds dynamic Avg Daily Trades stat cards to weekly HTML reports.

Reads a TradingView strategy CSV, computes avg daily trades (total / longs / shorts),
then patches one or more HTML report files with:
  - A filter bar (ALL / LONGS / SHORTS buttons)
  - A stats-row showing avg daily trades that updates dynamically on filter change

Usage:
    python3 patch_reports.py --csv path/to/trades.csv --html report1.html [report2.html ...]

Example — patch all Week 16 NQ reports:
    python3 patch_reports.py \\
        --csv ../data/raw-csvs/MNQ-04.13-17.26.Rmv20th.30-sec-or-rotations-3bar.Core_CME_MINI_MNQ1!_2026-04-20_d67cd.csv \\
        --html ../reports/Week16.html \\
                "../reports/MNQ Weekly snapshot-week16-04.13-04.17.26.html" \\
                "../reports/MNQ Weekly snapshot-week16-04.13-17.26.html" \\
                "../../../../../../Documents/GitHub/Trading-Strategy-Reports/30-sec-or-ladder-rotations/reports/weekly/week16.html" \\
                "../../../../../../Documents/GitHub/Trading-Strategy-Reports/reports/nq/week16/index.html"
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def compute_daily_data(csv_path: str) -> dict:
    """
    Read a TradingView strategy CSV and return per-day trade counts:
        { "2026-04-13": { "total": 9, "longs": 7, "shorts": 2 }, ... }
    """
    try:
        import pandas as pd
    except ImportError:
        sys.exit("pandas is required — run: pip install pandas")

    df = pd.read_csv(csv_path)

    # Filter to entry trades only (ignore exit rows)
    if "Type" not in df.columns:
        sys.exit(f"ERROR: no 'Type' column found in {csv_path}. Columns: {df.columns.tolist()}")

    entries = df[df["Type"].str.contains("Entry", na=False, case=False)].copy()

    # Determine direction from Type value ("Entry long" → Long, "Entry short" → Short)
    entries["direction"] = entries["Type"].str.lower().apply(
        lambda t: "Long" if "long" in t else ("Short" if "short" in t else "Unknown")
    )

    # Extract trade date (column is "Date and time" in TradingView exports)
    date_col = next(
        (c for c in df.columns if "date" in c.lower() or "time" in c.lower()),
        None
    )
    if not date_col:
        sys.exit(f"ERROR: no date/time column found. Columns: {df.columns.tolist()}")

    import pandas as pd  # already imported above but re-import for clarity
    entries["trade_date"] = pd.to_datetime(entries[date_col]).dt.strftime("%Y-%m-%d")

    days: dict = {}
    for day, group in entries.groupby("trade_date"):
        days[str(day)] = {
            "total": int(len(group)),
            "longs": int((group["direction"] == "Long").sum()),
            "shorts": int((group["direction"] == "Short").sum()),
        }

    return days


def compute_averages(days: dict) -> dict:
    if not days:
        return {"total": 0.0, "longs": 0.0, "shorts": 0.0}
    n = len(days)
    return {
        "total": round(sum(d["total"] for d in days.values()) / n, 1),
        "longs": round(sum(d["longs"] for d in days.values()) / n, 1),
        "shorts": round(sum(d["shorts"] for d in days.values()) / n, 1),
    }


# ---------------------------------------------------------------------------
# HTML patch generation
# ---------------------------------------------------------------------------

INSERTION_MARKER = 'Max Drawdown</div></div>\n</div>'

def build_patch(days: dict, avgs: dict) -> str:
    """Build the HTML + JS snippet to insert after the existing stats-row."""
    daily_json = json.dumps(days)

    return f"""
<div id="avg-daily-filter-bar" style="display:flex;gap:8px;margin:14px 0 6px 0;align-items:center;">
  <span style="color:#9399b2;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">Avg Daily Trades</span>
  <button class="adf-btn adf-active" data-dir="all"
          onclick="setAvgDailyFilter('all',this)"
          style="background:#45475a;color:#cdd6f4;border:1px solid #585b70;padding:3px 13px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">ALL</button>
  <button class="adf-btn" data-dir="longs"
          onclick="setAvgDailyFilter('longs',this)"
          style="background:#313244;color:#89dceb;border:1px solid #45475a;padding:3px 13px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">LONGS</button>
  <button class="adf-btn" data-dir="shorts"
          onclick="setAvgDailyFilter('shorts',this)"
          style="background:#313244;color:#f9e2af;border:1px solid #45475a;padding:3px 13px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;">SHORTS</button>
</div>
<div class="stats-row" id="avg-daily-row">
  <div class="stat">
    <div class="val" id="avgDailyTotal" style="color:#cdd6f4">{avgs['total']}</div>
    <div class="lbl">Avg Daily Trades</div>
  </div>
  <div class="stat">
    <div class="val" id="avgDailyLongs" style="color:#89dceb">{avgs['longs']}</div>
    <div class="lbl">Avg Daily Longs</div>
  </div>
  <div class="stat">
    <div class="val" id="avgDailyShorts" style="color:#f9e2af">{avgs['shorts']}</div>
    <div class="lbl">Avg Daily Shorts</div>
  </div>
</div>
<script>
(function () {{
  var DAILY = {daily_json};
  var allDays = Object.values(DAILY);

  function avg(arr) {{
    if (!arr.length) return 0;
    var sum = arr.reduce(function (a, b) {{ return a + b; }}, 0);
    return Math.round(sum / arr.length * 10) / 10;
  }}

  window.setAvgDailyFilter = function (dir, btn) {{
    document.querySelectorAll('.adf-btn').forEach(function (b) {{
      b.style.background = '#313244';
      b.classList.remove('adf-active');
    }});
    btn.style.background = '#45475a';
    btn.classList.add('adf-active');

    var total, longs, shorts;

    if (dir === 'all') {{
      total  = avg(allDays.map(function (d) {{ return d.total; }}));
      longs  = avg(allDays.map(function (d) {{ return d.longs; }}));
      shorts = avg(allDays.map(function (d) {{ return d.shorts; }}));
    }} else if (dir === 'longs') {{
      var activeDays = allDays.filter(function (d) {{ return d.longs > 0; }});
      total  = avg(activeDays.map(function (d) {{ return d.longs; }}));
      longs  = total;
      shorts = 0;
    }} else {{
      var activeDays = allDays.filter(function (d) {{ return d.shorts > 0; }});
      total  = avg(activeDays.map(function (d) {{ return d.shorts; }}));
      longs  = 0;
      shorts = total;
    }}

    document.getElementById('avgDailyTotal').textContent  = total;
    document.getElementById('avgDailyLongs').textContent  = longs;
    document.getElementById('avgDailyShorts').textContent = shorts;
  }};
}})();
</script>
"""


def patch_html(html_path: Path, days: dict, avgs: dict) -> None:
    content = html_path.read_text(encoding="utf-8")

    if "avg-daily-row" in content:
        print(f"  [SKIP] Already patched: {html_path.name}")
        return

    if INSERTION_MARKER not in content:
        print(f"  [WARN] Insertion point not found in: {html_path.name}")
        return

    patch = build_patch(days, avgs)
    content = content.replace(INSERTION_MARKER, INSERTION_MARKER + patch, 1)
    html_path.write_text(content, encoding="utf-8")
    print(f"  [OK]   Patched: {html_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add dynamic Avg Daily Trades cards to weekly HTML reports."
    )
    parser.add_argument("--csv", required=True, help="Path to TradingView trade CSV")
    parser.add_argument("--html", nargs="+", required=True, help="One or more HTML report files to patch")
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        sys.exit(f"ERROR: CSV not found: {csv_path}")

    print(f"Reading CSV: {csv_path.name}")
    days = compute_daily_data(str(csv_path))
    avgs = compute_averages(days)

    print(f"  Trading days: {len(days)}")
    for day, counts in sorted(days.items()):
        print(f"    {day}  total={counts['total']}  longs={counts['longs']}  shorts={counts['shorts']}")
    print(f"  Averages → total={avgs['total']}  longs={avgs['longs']}  shorts={avgs['shorts']}")
    print()

    for html_arg in args.html:
        html_path = Path(html_arg).expanduser().resolve()
        if not html_path.exists():
            print(f"  [MISS] File not found: {html_path}")
            continue
        patch_html(html_path, days, avgs)


if __name__ == "__main__":
    main()
