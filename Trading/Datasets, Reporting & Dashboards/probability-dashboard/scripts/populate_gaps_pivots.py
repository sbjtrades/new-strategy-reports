#!/usr/bin/env python3
"""
populate_gaps_pivots.py
-----------------------
Reads NQ_Daily / ES_Daily from the Master Sheet, computes Gaps and Pivots
for every day, and writes to NQ_Gaps, ES_Gaps, NQ_Pivots, ES_Pivots.

Gaps:
  - Gap (pts)       = Open - Prev Close
  - Gap Direction   = UP / DOWN / FLAT
  - Gap % of Range  = Gap / Prev Day Range
  - Filled Y/N      = Low <= PrevClose (up gap) or High >= PrevClose (down gap)
  - Close vs Gap    = Above gap / Filled / Below gap

Pivots (standard floor pivot, calculated from PREV day OHLC):
  PP = (H + L + C) / 3
  R1 = 2*PP - L  |  R2 = PP + (H-L)  |  R3 = H + 2*(PP-L)
  S1 = 2*PP - H  |  S2 = PP - (H-L)  |  S3 = L - 2*(H-PP)
  Tagged = today's high/low swept through the level
"""

from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID   = "18yyXZfceJJQLvxVM8z2eoPb-H_VVw2pt_Lg61iZGtMw"
CREDS_FILE = Path(__file__).parent.parent / "data" / "datasets-dashboard-google-cloud-api-3dda84cfeeb8.json"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets"]

HEADER_STYLE = {
    "textFormat": {"bold": True},
    "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18},
    "horizontalAlignment": "CENTER"
}

DAYS_OF_WEEK = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4,
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4
}

from datetime import datetime

def dow(date_str):
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return d.strftime("%a")
    except:
        return ""

def r(v, dec=2):
    try:
        return round(float(v), dec)
    except:
        return ""

def tagged(level, day_high, day_low):
    """Did the day's range sweep through this pivot level?"""
    try:
        return "Y" if float(day_low) <= float(level) <= float(day_high) else "N"
    except:
        return "N"

def read_daily(ws):
    """Read daily tab, return list of dicts skipping header."""
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]

def compute_gaps(daily_rows):
    out = []
    for i in range(1, len(daily_rows)):
        prev = daily_rows[i - 1]
        cur  = daily_rows[i]
        try:
            prev_close = float(prev["Close"])
            prev_high  = float(prev["High"])
            prev_low   = float(prev["Low"])
            o = float(cur["Open"])
            h = float(cur["High"])
            l = float(cur["Low"])
            c = float(cur["Close"])
        except:
            continue

        gap      = r(o - prev_close)
        prev_rng = r(prev_high - prev_low)
        gap_dir  = "UP" if gap > 0.5 else ("DOWN" if gap < -0.5 else "FLAT")
        gap_pct  = r((gap / prev_rng * 100) if prev_rng else 0)

        if gap_dir == "UP":
            filled = "Y" if l <= prev_close else "N"
            close_rel = "Above Gap" if c > o else ("Filled" if c <= prev_close else "Inside Gap")
        elif gap_dir == "DOWN":
            filled = "Y" if h >= prev_close else "N"
            close_rel = "Below Gap" if c < o else ("Filled" if c >= prev_close else "Inside Gap")
        else:
            filled    = "N/A"
            close_rel = "No Gap"

        out.append([
            cur["Date"], dow(cur["Date"]),
            r(prev_close), r(o), gap, gap_dir,
            gap_pct, filled, "", "",   # Fill Time + Session = manual
            close_rel
        ])
    return out

def compute_pivots(daily_rows):
    out = []
    for i in range(1, len(daily_rows)):
        prev = daily_rows[i - 1]
        cur  = daily_rows[i]
        try:
            ph = float(prev["High"])
            pl = float(prev["Low"])
            pc = float(prev["Close"])
            h  = float(cur["High"])
            l  = float(cur["Low"])
            c  = float(cur["Close"])
        except:
            continue

        pp = r((ph + pl + pc) / 3)
        r1 = r(2*pp - pl)
        r2 = r(pp + (ph - pl))
        r3 = r(ph + 2*(pp - pl))
        s1 = r(2*pp - ph)
        s2 = r(pp - (ph - pl))
        s3 = r(pl - 2*(ph - pp))

        levels = {"PP": pp, "R1": r1, "R2": r2, "R3": r3,
                  "S1": s1, "S2": s2, "S3": s3}

        tagged_names = [name for name, val in levels.items() if tagged(val, h, l) == "Y"]
        tagged_count = len(tagged_names)
        tagged_str   = ", ".join(tagged_names) if tagged_names else "None"

        # First touch direction: lowest R-level tagged or highest S-level tagged
        r_tagged = [n for n in tagged_names if n.startswith("R")]
        s_tagged = [n for n in tagged_names if n.startswith("S")]
        if r_tagged and s_tagged:
            first_dir = "Both"
        elif r_tagged:
            first_dir = "UP"
        elif s_tagged:
            first_dir = "DOWN"
        else:
            first_dir = "None"

        close_vs_pp = "Above" if c > pp else ("Below" if c < pp else "At")

        out.append([
            cur["Date"], dow(cur["Date"]),
            pp, r1, r2, r3, s1, s2, s3,
            tagged_count, tagged_str,
            first_dir, close_vs_pp
        ])
    return out

def write_tab(ws, headers, rows):
    ws.clear()
    ws.update([headers] + rows, value_input_option="USER_ENTERED")
    ws.freeze(rows=1)
    ws.format("1:1", HEADER_STYLE)
    print(f"    → {len(rows)} rows written")

GAP_HEADERS = [
    "Date", "DOW",
    "Prev Close", "Open", "Gap (pts)", "Gap Direction",
    "Gap % of Prev Range", "Filled Y/N", "Fill Time", "Fill Session",
    "Close Relationship to Gap"
]
PIVOT_HEADERS = [
    "Date", "DOW",
    "PP", "R1", "R2", "R3", "S1", "S2", "S3",
    "Levels Tagged (count)", "Levels Tagged (names)",
    "First Touch Direction", "Day Close vs PP"
]

def main():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)
    print(f"Sheet: {sh.title}\n")

    for instrument in ["NQ", "ES"]:
        print(f"── {instrument} ──────────────")

        daily_ws = sh.worksheet(f"{instrument}_Daily")
        daily_rows = read_daily(daily_ws)
        print(f"  Read {len(daily_rows)} daily rows")

        # Gaps
        print(f"  Writing {instrument}_Gaps...")
        gap_rows = compute_gaps(daily_rows)
        write_tab(sh.worksheet(f"{instrument}_Gaps"), GAP_HEADERS, gap_rows)

        # Pivots
        print(f"  Writing {instrument}_Pivots...")
        pivot_rows = compute_pivots(daily_rows)
        write_tab(sh.worksheet(f"{instrument}_Pivots"), PIVOT_HEADERS, pivot_rows)

        print()

    print("Done.")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")

if __name__ == "__main__":
    main()
