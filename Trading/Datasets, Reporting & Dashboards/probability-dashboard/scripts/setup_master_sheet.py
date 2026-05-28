#!/usr/bin/env python3
"""
setup_master_sheet.py
---------------------
One-time setup: creates all tabs in the Master Google Sheet and
populates them with historical OHLC data from yfinance.

Run once to initialize. After that, use update_master_sheet.py weekly.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID = "18yyXZfceJJQLvxVM8z2eoPb-H_VVw2pt_Lg61iZGtMw"
CREDS_FILE = Path(__file__).parent.parent / "data" / "datasets-dashboard-google-cloud-api-3dda84cfeeb8.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# yfinance tickers (continuous front-month futures)
TICKERS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
}

# How much history to load on first setup
DAILY_DAYS   = 90   # ~3 months of daily bars
WEEKLY_WEEKS = 52   # ~1 year of weekly bars
MONTHLY_MONTHS = 24 # ~2 years of monthly bars

# Tab names
TABS = [
    "NQ_Daily", "NQ_Weekly", "NQ_Monthly",
    "ES_Daily", "ES_Weekly", "ES_Monthly",
]

DAILY_HEADERS   = ["Date", "Open", "High", "Low", "Close", "Volume", "Change %", "Range (pts)", "Direction"]
WEEKLY_HEADERS  = ["Week Start", "Open", "High", "Low", "Close", "Weekly Change %", "Range (pts)", "Direction"]
MONTHLY_HEADERS = ["Month", "Open", "High", "Low", "Close", "Monthly Change %", "Range (pts)", "Direction"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def connect():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    return gspread.authorize(creds)


def round2(v):
    try:
        return round(float(v), 2)
    except:
        return ""


def fetch_daily(ticker_sym, days=DAILY_DAYS):
    end   = datetime.today()
    start = end - timedelta(days=days + 30)  # buffer for weekends/holidays
    df = yf.download(ticker_sym, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty:
        return []

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"]).tail(days)
    rows = []
    prev_close = None
    for date, row in df.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        vol = row.get("Volume", "")
        chg = round2(((c - prev_close) / prev_close * 100)) if prev_close else ""
        rng = round2(h - l)
        direction = "UP" if (prev_close and c >= prev_close) else ("DOWN" if prev_close else "")
        rows.append([
            date.strftime("%Y-%m-%d"),
            round2(o), round2(h), round2(l), round2(c),
            int(vol) if vol else "",
            chg, rng, direction
        ])
        prev_close = c
    return rows


def fetch_weekly(ticker_sym, weeks=WEEKLY_WEEKS):
    end   = datetime.today()
    start = end - timedelta(weeks=weeks + 4)
    df = yf.download(ticker_sym, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), interval="1wk",
                     progress=False, auto_adjust=True)
    if df.empty:
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"]).tail(weeks)
    rows = []
    prev_close = None
    for date, row in df.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        chg = round2(((c - prev_close) / prev_close * 100)) if prev_close else ""
        rng = round2(h - l)
        direction = "UP" if (prev_close and c >= prev_close) else ("DOWN" if prev_close else "")
        rows.append([
            date.strftime("%Y-%m-%d"),
            round2(o), round2(h), round2(l), round2(c),
            chg, rng, direction
        ])
        prev_close = c
    return rows


def fetch_monthly(ticker_sym, months=MONTHLY_MONTHS):
    end   = datetime.today()
    start = end - timedelta(days=months * 31 + 60)
    df = yf.download(ticker_sym, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), interval="1mo",
                     progress=False, auto_adjust=True)
    if df.empty:
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"]).tail(months)
    rows = []
    prev_close = None
    for date, row in df.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        chg = round2(((c - prev_close) / prev_close * 100)) if prev_close else ""
        rng = round2(h - l)
        direction = "UP" if (prev_close and c >= prev_close) else ("DOWN" if prev_close else "")
        rows.append([
            date.strftime("%Y-%m"),
            round2(o), round2(h), round2(l), round2(c),
            chg, rng, direction
        ])
        prev_close = c
    return rows


def ensure_tab(spreadsheet, title, existing_titles):
    """Create tab if it doesn't exist, return worksheet."""
    if title not in existing_titles:
        ws = spreadsheet.add_worksheet(title=title, rows=500, cols=20)
        print(f"  Created tab: {title}")
    else:
        ws = spreadsheet.worksheet(title)
        print(f"  Found tab:   {title}")
    return ws


def write_tab(ws, headers, rows):
    """Clear tab, write headers + data, freeze header row, bold headers."""
    ws.clear()
    all_rows = [headers] + rows
    ws.update(all_rows, value_input_option="USER_ENTERED")

    # Freeze header row
    ws.freeze(rows=1)

    # Bold header row
    ws.format("1:1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
        "horizontalAlignment": "CENTER"
    })

    print(f"    → {len(rows)} data rows written")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Connecting to Google Sheets...")
    gc = connect()
    sh = gc.open_by_key(SHEET_ID)
    existing = [ws.title for ws in sh.worksheets()]
    print(f"Sheet found: {sh.title}")
    print(f"Existing tabs: {existing}\n")

    for instrument, ticker in TICKERS.items():
        print(f"── {instrument} ({ticker}) ──────────────")

        # Daily
        tab_name = f"{instrument}_Daily"
        ws = ensure_tab(sh, tab_name, existing)
        rows = fetch_daily(ticker)
        write_tab(ws, DAILY_HEADERS, rows)

        # Weekly
        tab_name = f"{instrument}_Weekly"
        ws = ensure_tab(sh, tab_name, existing)
        rows = fetch_weekly(ticker)
        write_tab(ws, WEEKLY_HEADERS, rows)

        # Monthly
        tab_name = f"{instrument}_Monthly"
        ws = ensure_tab(sh, tab_name, existing)
        rows = fetch_monthly(ticker)
        write_tab(ws, MONTHLY_HEADERS, rows)

        print()

    # Remove default "Sheet1" if it's still empty
    if "Sheet1" in [ws.title for ws in sh.worksheets()]:
        try:
            sh.del_worksheet(sh.worksheet("Sheet1"))
            print("Removed default Sheet1")
        except:
            pass

    print("\nDone. Master sheet initialized.")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
