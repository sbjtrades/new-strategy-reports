# SBJ Trading Dashboards — Project Overview

Live site: https://sbjtrades.github.io/new-strategy-reports/

---

## Dashboards

### NQ / ES Probability Dashboard
**Path:** `Trading/Datasets, Reporting & Dashboards/probability-dashboard/probability-dashboard.html`
**URL:** https://sbjtrades.github.io/new-strategy-reports/Trading/Datasets,%20Reporting%20%26%20Dashboards/probability-dashboard/probability-dashboard.html

8-tab probabilistic reference dashboard for NQ/MNQ and ES/MES futures day trading.
Tabs: OHLC · ALN Sessions · Opening Range · Initial Balance · Gaps · LOI · Pivots · Ladders

**Data files read by the dashboard:**
- `data/stats/MNQ_stats.json` / `MES_stats.json` — all tab stats
- `data/stats/NQ_history.json` / `ES_history.json` — OHLC history tables

**Google Sheet data warehouse:** "NQ/ES Dashboard Data 2026" (18 tabs, updated weekly)

---

### 30 Sec OR Dashboard V2
**Path:** `Trading/Datasets, Reporting & Dashboards/or-dashboard-v2/unified-dashboard.html`
**URL:** https://sbjtrades.github.io/new-strategy-reports/Trading/Datasets,%20Reporting%20%26%20Dashboards/or-dashboard-v2/unified-dashboard.html

Opening range rotation strategy dashboard — 30-second bar analysis for MNQ.

Data: `Trading/or-dashboard-v2/dashboard_data.json`

---

## Repo Structure

```
Desktop/ (git root)
├── index.html
├── PROJECT_OVERVIEW.md                        ← this file
└── Trading/
    └── Datasets, Reporting & Dashboards/
        ├── probability-dashboard/
        │   ├── probability-dashboard.html     ← the dashboard
        │   ├── data/stats/                    ← JSON data (git-tracked)
        │   │   ├── MNQ_stats.json
        │   │   ├── MES_stats.json
        │   │   ├── NQ_history.json
        │   │   └── ES_history.json
        │   └── scripts/                       ← update scripts
        │       ├── export_history_json.py     ← generates history JSON
        │       └── update_master_sheet.py     ← populates Google Sheet
        └── or-dashboard-v2/
            ├── unified-dashboard.html
            └── dashboard_data.json
```

**Vault pipeline root:**
`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SJ Work Vault/04 - reporting-dashboards/probability-dashboard/v1/`

---

## Weekly Update — Probability Dashboard (Full Pipeline)

**Python:** `{vault}/.venv/bin/python`
**NEVER** use `git add -A` from `~/Desktop` — always add specific files.

### Step 1 — Export from TradingView
Drop the following CSVs into `v1/data/raw/` (replace previous copies):

| Export | What it is |
|---|---|
| `MNQ-Daily-*.csv` | NQ full daily OHLC history |
| `MES-Daily-*.csv` | ES full daily OHLC history |
| `MNQ OR's + IB + Extensions.*.csv` | NQ Opening Range + Initial Balance |
| `MES OR's + IB + Extensions.*.csv` | ES Opening Range + Initial Balance |
| `MNQ - Key LOI's-4Hr-ETH-*.csv` | NQ Levels of Interest (full history) |
| `MNQ - Key LOI's-15Min-*.csv` | NQ LOI (recent, 15-min) |
| `MES - Key LOI's-4Hr-ETH-*.csv` | ES LOI (full history) |
| `MES- Key LOI's-15Min-*.csv` | ES LOI (recent, 15-min) |
| `MNQ-Week##.Dates.csv` | NQ weekly OR ladder snapshot |
| `MES-Week##.Dates.csv` | ES weekly OR ladder snapshot |

### Step 2 — Process raw CSVs → processed/
```bash
cd "{vault}/04 - reporting-dashboards/probability-dashboard/v1"
{vault}/.venv/bin/python scripts/process_raw.py
# Refreshes all processed/*.csv
```

### Step 3 — Generate stats JSON
```bash
{vault}/.venv/bin/python scripts/generate_stats.py
# Outputs: v1/data/stats/MNQ_stats.json + MES_stats.json
```
Copy to git repo:
```bash
cp "{vault}/04 - reporting-dashboards/probability-dashboard/v1/data/stats/MNQ_stats.json" \
   ~/Desktop/Trading/Datasets*/probability-dashboard/data/stats/
cp "{vault}/04 - reporting-dashboards/probability-dashboard/v1/data/stats/MES_stats.json" \
   ~/Desktop/Trading/Datasets*/probability-dashboard/data/stats/
```

### Step 4 — Generate OHLC history JSON (dashboard history tables)
```bash
cd ~/Desktop/Trading/Datasets*/probability-dashboard
{vault}/.venv/bin/python scripts/export_history_json.py
# Outputs: data/stats/NQ_history.json + ES_history.json
# Note: Sunday futures sessions correctly bucketed into the following week
```

### Step 5 — Update Google Sheet (all 18 tabs)
```bash
{vault}/.venv/bin/python scripts/update_master_sheet.py
# Populates all 18 tabs in "NQ/ES Dashboard Data 2026"
# Newest-first sort, yellow bold header row
# ~25 seconds (rate-limited API calls)
```

### Step 6 — Commit and push to GitHub Pages
```bash
cd ~/Desktop
git add "Trading/Datasets, Reporting & Dashboards/probability-dashboard/data/stats/MNQ_stats.json"
git add "Trading/Datasets, Reporting & Dashboards/probability-dashboard/data/stats/MES_stats.json"
git add "Trading/Datasets, Reporting & Dashboards/probability-dashboard/data/stats/NQ_history.json"
git add "Trading/Datasets, Reporting & Dashboards/probability-dashboard/data/stats/ES_history.json"
git commit -m "Data: weekly update Week ## — YYYY-MM-DD"
git push
# GitHub Pages live within ~1 minute
```

---

## Google Sheet

**Sheet name:** "NQ/ES Dashboard Data 2026"
**Sheet ID:** `18yyXZfceJJQLvxVM8z2eoPb-H_VVw2pt_Lg61iZGtMw`
**Service account:** `datasets-dashboards@python-nq-data.iam.gserviceaccount.com`
**Credentials:** `data/datasets-dashboard-google-cloud-api-3dda84cfeeb8.json` (gitignored)

18 tabs (9 NQ + 9 ES): Daily · Weekly · Monthly · ALN · Gaps · LOI · Pivots · Ladder · IB

---

## Updating OR Dashboard Data

1. Run `update_dashboard_data.py`
2. Copy output → `Trading/Datasets, Reporting & Dashboards/or-dashboard-v2/dashboard_data.json`
3. Commit and push
