# SBJ Trading Dashboards — Project Overview

Live site: https://sbjtrades.github.io/new-strategy-reports/

---

## Dashboards

### NQ / ES Probability Dashboard
**Path:** `Trading/probability-dashboard/probability-dashboard.html`  
**URL:** https://sbjtrades.github.io/new-strategy-reports/Trading/probability-dashboard/probability-dashboard.html

8-tab probabilistic reference dashboard for NQ/MNQ and ES/MES futures day trading.  
Tabs: OHLC · ALN Sessions · Opening Range · Initial Balance · Gaps · LOI · Pivots · Ladders

Data: `Trading/probability-dashboard/data/stats/MNQ_stats.json` / `MES_stats.json`

---

### 30 Sec OR Dashboard V2
**Path:** `Trading/or-dashboard-v2/unified-dashboard.html`  
**URL:** https://sbjtrades.github.io/new-strategy-reports/Trading/or-dashboard-v2/unified-dashboard.html

Opening range rotation strategy dashboard — 30-second bar analysis for MNQ.

Data: `Trading/or-dashboard-v2/dashboard_data.json`

---

## Repo Structure

```
Desktop/ (git root)
├── index.html                      ← landing page (links to both dashboards)
├── PROJECT_OVERVIEW.md             ← this file
├── Trading/
│   ├── probability-dashboard/      ← NQ/ES Probability Dashboard
│   │   ├── probability-dashboard.html
│   │   └── data/stats/
│   └── or-dashboard-v2/            ← 30 Sec OR Dashboard V2
│       ├── unified-dashboard.html
│       └── dashboard_data.json
```

## Updating Data

**Probability dashboard stats:**
1. Export CSVs from TradingView → vault raw data folders
2. Run generate_stats.py in vault scripts
3. Copy MNQ_stats.json / MES_stats.json → Trading/probability-dashboard/data/stats/
4. cd ~/Desktop && git add Trading/probability-dashboard/data/stats/ && git commit && git push

**OR dashboard data:**
1. Run update_dashboard_data.py
2. Copy output → Trading/or-dashboard-v2/dashboard_data.json
3. Commit and push
