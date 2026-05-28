#!/usr/bin/env python3
"""
add_sheet_tabs.py
-----------------
Adds all remaining data tabs to the Master Google Sheet with correct headers.
Run once. Safe to re-run — skips tabs that already exist.
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

# ── Tab definitions ────────────────────────────────────────────────────────────
TABS = {
    # ALN Sessions
    "NQ_ALN": [
        "Date", "DOW",
        "Asia High", "Asia Low", "Asia Range (pts)", "Asia Close",
        "London High", "London Low", "London Range (pts)",
        "NY Open", "NY Open vs Asia Close", "NY Open vs Asia Range",
        "Session Bias", "Notes"
    ],
    "ES_ALN": [
        "Date", "DOW",
        "Asia High", "Asia Low", "Asia Range (pts)", "Asia Close",
        "London High", "London Low", "London Range (pts)",
        "NY Open", "NY Open vs Asia Close", "NY Open vs Asia Range",
        "Session Bias", "Notes"
    ],

    # Gaps
    "NQ_Gaps": [
        "Date", "DOW",
        "Prev Close", "Open", "Gap (pts)", "Gap Direction",
        "Gap % of Prev Range", "Filled Y/N", "Fill Time", "Fill Session",
        "Close Relationship to Gap"
    ],
    "ES_Gaps": [
        "Date", "DOW",
        "Prev Close", "Open", "Gap (pts)", "Gap Direction",
        "Gap % of Prev Range", "Filled Y/N", "Fill Time", "Fill Session",
        "Close Relationship to Gap"
    ],

    # LOI (Levels of Interest) — one row per level per day
    "NQ_LOI": [
        "Date", "DOW", "Level Name", "Level Price",
        "Level Type", "Timeframe",
        "Tagged Y/N", "Session Tagged", "Reaction (Bounce/Break/None)",
        "Follow-Through (pts)", "Notes"
    ],
    "ES_LOI": [
        "Date", "DOW", "Level Name", "Level Price",
        "Level Type", "Timeframe",
        "Tagged Y/N", "Session Tagged", "Reaction (Bounce/Break/None)",
        "Follow-Through (pts)", "Notes"
    ],

    # Pivots
    "NQ_Pivots": [
        "Date", "DOW",
        "PP", "R1", "R2", "R3", "S1", "S2", "S3",
        "Levels Tagged (count)", "Levels Tagged (names)",
        "First Touch Direction", "Day Close vs PP"
    ],
    "ES_Pivots": [
        "Date", "DOW",
        "PP", "R1", "R2", "R3", "S1", "S2", "S3",
        "Levels Tagged (count)", "Levels Tagged (names)",
        "First Touch Direction", "Day Close vs PP"
    ],

    # OR Ladder Rotations
    "NQ_Ladder": [
        "Date", "DOW",
        "OR High", "OR Low", "OR Range (pts)",
        "UL1 Tagged", "UL2 Tagged", "UL3 Tagged",
        "DL1 Tagged", "DL2 Tagged", "DL3 Tagged",
        "Max Extension Level", "Max Extension Direction",
        "Rotation Count", "OR Breakout Direction",
        "OR Breakout Time", "Day Close vs OR"
    ],
    "ES_Ladder": [
        "Date", "DOW",
        "OR High", "OR Low", "OR Range (pts)",
        "UL1 Tagged", "UL2 Tagged", "UL3 Tagged",
        "DL1 Tagged", "DL2 Tagged", "DL3 Tagged",
        "Max Extension Level", "Max Extension Direction",
        "Rotation Count", "OR Breakout Direction",
        "OR Breakout Time", "Day Close vs OR"
    ],

    # IB (Initial Balance)
    "NQ_IB": [
        "Date", "DOW",
        "IB High", "IB Low", "IB Range (pts)",
        "IB Extension High Y/N", "IB Extension Low Y/N",
        "IB Extension % (pts above/below)", "Extension Direction",
        "Extension Session", "Day Close vs IB"
    ],
    "ES_IB": [
        "Date", "DOW",
        "IB High", "IB Low", "IB Range (pts)",
        "IB Extension High Y/N", "IB Extension Low Y/N",
        "IB Extension % (pts above/below)", "Extension Direction",
        "Extension Session", "Day Close vs IB"
    ],
}

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)

    existing = {ws.title for ws in sh.worksheets()}
    print(f"Sheet: {sh.title}")
    print(f"Existing tabs: {sorted(existing)}\n")

    for tab_name, headers in TABS.items():
        if tab_name in existing:
            print(f"  SKIP  {tab_name} (already exists)")
            continue

        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(headers) + 2)
        ws.update([headers], value_input_option="USER_ENTERED")
        ws.freeze(rows=1)
        ws.format("1:1", HEADER_STYLE)
        print(f"  ADDED {tab_name}  ({len(headers)} columns)")

    print(f"\nDone. {len(TABS)} tabs configured.")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")

if __name__ == "__main__":
    main()
