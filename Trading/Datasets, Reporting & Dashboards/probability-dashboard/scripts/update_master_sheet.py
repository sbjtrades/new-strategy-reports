#!/usr/bin/env python3
"""
update_master_sheet.py
----------------------
Weekly update: reads all processed CSVs → overwrites all 18 tabs in
the Master Google Sheet "NQ/ES Dashboard Data 2026".

Run each week after process_raw.py:
    python3 scripts/update_master_sheet.py

Tabs updated:
  NQ_Daily, NQ_Weekly, NQ_Monthly  ← MNQ_daily_ohlc.csv
  ES_Daily, ES_Weekly, ES_Monthly  ← MES_daily_ohlc.csv
  NQ_ALN,   ES_ALN                 ← *_daily_aln.csv
  NQ_Gaps,  ES_Gaps                ← *_daily_gaps.csv
  NQ_LOI,   ES_LOI                 ← *_daily_loi.csv
  NQ_Pivots,ES_Pivots              ← *_daily_pivots.csv
  NQ_Ladder,ES_Ladder              ← *_daily_ladders.csv
  NQ_IB,    ES_IB                  ← IB columns from *_daily_or_ib.csv
"""

import time
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID   = "18yyXZfceJJQLvxVM8z2eoPb-H_VVw2pt_Lg61iZGtMw"
CREDS_FILE = Path(__file__).parent.parent / "data" / "datasets-dashboard-google-cloud-api-3dda84cfeeb8.json"
PROC_DIR   = Path("/Users/shawnjudge/Library/Mobile Documents/iCloud~md~obsidian/Documents/SJ Work Vault/04 - reporting-dashboards/probability-dashboard/v1/data/processed")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# prefix → instrument filename prefix
INST = {"NQ": "MNQ", "ES": "MES"}

# Sheets API allows ~100 write requests per 100s; pause between tabs to stay safe
PAUSE = 1.2


# ── Helpers ───────────────────────────────────────────────────────────────────

def connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def read_csv(instrument, suffix):
    """Load a processed CSV, return DataFrame. Empty DF if missing."""
    path = PROC_DIR / f"{instrument}_{suffix}.csv"
    if not path.exists():
        print(f"    [WARN] not found: {path.name}")
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    return df


def clean_val(v):
    """Convert a single cell value to a Sheets-safe type."""
    if v is None:
        return ""
    # NaN / inf check for floats
    if isinstance(v, float):
        import math
        if math.isnan(v) or math.isinf(v):
            return ""
        return v
    if isinstance(v, (int, bool)):
        return v
    return str(v)


def df_to_rows(df, date_col="date"):
    """Convert DataFrame → [headers, row, row, ...] ready for gspread.update().
    Sorts by date descending (newest first) if the date column exists."""
    if date_col in df.columns:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values(date_col, ascending=False).reset_index(drop=True)
        df[date_col] = df[date_col].dt.strftime("%Y-%m-%d")
    headers = list(df.columns)
    data = [[clean_val(v) for v in row] for row in df.itertuples(index=False)]
    return [headers] + data


HEADER_FMT = {
    "backgroundColor":    {"red": 0.98, "green": 0.82, "blue": 0.25},   # golden yellow
    "textFormat":         {"bold": True, "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}},
    "horizontalAlignment": "CENTER",
}


def write_tab(ws, data, tab_name):
    """Clear a worksheet, write data (header + rows), format header row yellow."""
    n_rows = len(data)
    n_cols = len(data[0]) if data else 1

    ws.clear()
    time.sleep(0.3)

    # Ensure the sheet is large enough
    if ws.row_count < n_rows + 5 or ws.col_count < n_cols:
        ws.resize(rows=n_rows + 20, cols=n_cols)
        time.sleep(0.3)

    ws.update(data, value_input_option="USER_ENTERED")
    time.sleep(0.3)

    # Yellow header
    ws.format("1:1", HEADER_FMT)

    print(f"  ✓  {tab_name:<18}  {n_rows - 1:>5} rows  ×  {n_cols} cols")
    time.sleep(PAUSE)


# ── Aggregations ──────────────────────────────────────────────────────────────

def aggregate_weekly(ohlc_df):
    """Group daily OHLC → weekly bars (oldest first)."""
    df = ohlc_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    # NQ futures: Sunday PM session is the open of the following week — shift +1 day
    date_adj = df["date"] + pd.to_timedelta((df["date"].dt.dayofweek == 6).astype(int), unit="D")
    df["week"] = date_adj.dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")

    agg = df.groupby("week", sort=True).agg(
        open=("open",  "first"),
        high=("high",  "max"),
        low=("low",   "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        avg_daily_range=("daily_range", "mean"),
        sessions=("date", "count"),
    ).reset_index().rename(columns={"week": "date"})

    agg["weekly_chg_pct"] = (
        (agg["close"] - agg["close"].shift(1)) / agg["close"].shift(1) * 100
    ).round(3)
    agg["direction"] = agg["weekly_chg_pct"].apply(
        lambda x: "UP" if pd.notna(x) and x >= 0 else ("DOWN" if pd.notna(x) else "")
    )
    return agg.round(2)


def aggregate_monthly(ohlc_df):
    """Group daily OHLC → monthly bars (oldest first)."""
    df = ohlc_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.strftime("%Y-%m")

    agg = df.groupby("month", sort=True).agg(
        open=("open",  "first"),
        high=("high",  "max"),
        low=("low",   "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        avg_daily_range=("daily_range", "mean"),
        sessions=("date", "count"),
    ).reset_index().rename(columns={"month": "date"})

    agg["monthly_chg_pct"] = (
        (agg["close"] - agg["close"].shift(1)) / agg["close"].shift(1) * 100
    ).round(3)
    agg["direction"] = agg["monthly_chg_pct"].apply(
        lambda x: "UP" if pd.notna(x) and x >= 0 else ("DOWN" if pd.notna(x) else "")
    )
    return agg.round(2)


def extract_ib(or_ib_df):
    """Pull IB-relevant columns from the or_ib DataFrame."""
    base = [c for c in ["date", "instrument", "day_of_week"] if c in or_ib_df.columns]
    ib   = [c for c in or_ib_df.columns if c.startswith("ib_")]
    return or_ib_df[base + ib]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to Google Sheets...")
    gc    = connect()
    sh    = gc.open_by_key(SHEET_ID)
    ws_by = {ws.title: ws for ws in sh.worksheets()}
    print(f"Sheet : {sh.title}")
    print(f"Tabs  : {sorted(ws_by.keys())}\n")

    for prefix, instrument in INST.items():
        print(f"── {prefix} ({instrument}) ──────────────────────")

        # OHLC → Daily / Weekly / Monthly
        ohlc = read_csv(instrument, "daily_ohlc")
        if not ohlc.empty:
            write_tab(ws_by[f"{prefix}_Daily"],   df_to_rows(ohlc),                    f"{prefix}_Daily")
            write_tab(ws_by[f"{prefix}_Weekly"],  df_to_rows(aggregate_weekly(ohlc)),  f"{prefix}_Weekly")
            write_tab(ws_by[f"{prefix}_Monthly"], df_to_rows(aggregate_monthly(ohlc)), f"{prefix}_Monthly")

        # ALN sessions
        aln = read_csv(instrument, "daily_aln")
        if not aln.empty:
            write_tab(ws_by[f"{prefix}_ALN"], df_to_rows(aln), f"{prefix}_ALN")

        # Gaps
        gaps = read_csv(instrument, "daily_gaps")
        if not gaps.empty:
            write_tab(ws_by[f"{prefix}_Gaps"], df_to_rows(gaps), f"{prefix}_Gaps")

        # LOI (level of interest per day)
        loi = read_csv(instrument, "daily_loi")
        if not loi.empty:
            write_tab(ws_by[f"{prefix}_LOI"], df_to_rows(loi), f"{prefix}_LOI")

        # Pivots
        pivots = read_csv(instrument, "daily_pivots")
        if not pivots.empty:
            write_tab(ws_by[f"{prefix}_Pivots"], df_to_rows(pivots), f"{prefix}_Pivots")

        # OR Ladder
        ladders = read_csv(instrument, "daily_ladders")
        if not ladders.empty:
            write_tab(ws_by[f"{prefix}_Ladder"], df_to_rows(ladders), f"{prefix}_Ladder")

        # IB — extracted from or_ib CSV
        or_ib = read_csv(instrument, "daily_or_ib")
        if not or_ib.empty:
            ib = extract_ib(or_ib)
            write_tab(ws_by[f"{prefix}_IB"], df_to_rows(ib), f"{prefix}_IB")

        print()

    print("Done.")


if __name__ == "__main__":
    main()
