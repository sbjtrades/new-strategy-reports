# Trading Dashboard Project Overview

## Purpose
A **comprehensive trading analytics dashboard** for NQ/MNQ and ES/MES futures day traders using a probabilistic framework. The dashboard aggregates trade data and provides multi-dimensional analysis to identify patterns, optimize trading performance, and guide decision-making.

## Target User
- Intraday futures trader (NQ/MNQ and ES/MES focus)
- Uses ALN sessions, OR ladder analysis, initial balance (IB), HLOC patterns, and hourly structures
- Needs to extract actionable insights from historical trades across multiple timeframes

---

## Dashboard Architecture

### Frontend Stack
- **Single-page HTML5/CSS3/JavaScript** app: `unified-dashboard.html` (1900+ lines)
- **Plotly.js v2** for interactive charting
- **Dark theme** optimized for trading: #1e1e2e background, #a6e3a1 profit green, #f38ba8 loss red
- **Responsive grid layout** with collapsible sections

### Backend Stack
- **Python 3.9** data pipeline: `update_dashboard_data.py` (1300+ lines)
- **Pandas** for data manipulation
- **Data sources**: NQ/MNQ Excel exports + ES/MES TradingView CSV
- **Output**: Hierarchical JSON (8.1MB) with 3 trade-type variants at each level

### Data Architecture
**Hierarchical Structure**: Year → Quarter → Month → Week → Day

**Three Trade-Type Variants** at Every Period Level:
- `ladder_analysis` — all trades
- `ladder_analysis_directional` — Bull/Short setup entries only
- `ladder_analysis_reversals` — Reversal entries only

**Temporal Analysis** at All Period Levels:
- `by_day_of_week` — Mon-Fri performance metrics
- `by_hour` — hourly breakdown (9:00-16:00 trading hours)
- `by_trading_quarter` — 4 market phases (Opening, Lunch, Post-Lunch, Close)

---

## Key Features

### 1. **Overview Tab**
- Trade summary metrics (Total, Win%, P&L, Avg/Trade)
- Trade type breakdown (Primary Directional vs Reversals)
- Performance by instrument (NQ vs ES)
- Trade distribution by entry ladder and setup type
- Risk/reward distribution charts

### 2. **Ladder Analysis Tab**
- **Up Ladder Performance** (ORH → UL1 → UL10): Bull setup analysis
- **Down Ladder Performance** (ORL → DL1 → DL10): Short setup analysis
- P&L by ladder for both primary and reversal trades
- Win rate and trade count by ladder
- Avg win vs avg loss dollar values per ladder

### 3. **Entry Setup Analysis Tab**
- Entry setup types (Bull Setup, Short Setup, Reversals)
- P&L and win% for each setup category
- Gross profit/loss breakdown
- Trade count and average P&L per setup

### 4. **Time & Day Patterns Tab** *(Recently Enhanced)*
- **Day of Week** — Net P&L $ by day (Mon-Fri)
- **Trading Quarters** — Performance across 4 market phases
  - Q1: 09:30-11:30 (Opening)
  - Q2: 11:30-13:00 (Lunch Approach)
  - Q3: 13:00-15:00 (Post-Lunch)
  - Q4: 15:00-16:00 (Close)
- **Hourly Breakdown** — 7 individual hours with stat cards
  - 9:00-10:00 AM (flagged as ANOMALY in red)
  - 10:00-11:00 AM through 3:00-4:00 PM
- **Period Filtering** — All time patterns update based on Year/Quarter/Month/Week selection

### 5. **Instrument Selection**
- Toggle between NQ and ES futures
- Trade-type filter: All Trades / Primary (Directional) / Reversals Only
- Hierarchical period filters: Year → Quarter → Month → Week

---

## Recent Enhancements (Session 2026-04-26)

### Fixed Issues
1. ✅ **Weekly filtering loop** — Replaced broken `q = {}` with `foundWeek` boolean
2. ✅ **Missing trade-type variants** — Added directional and reversal analysis at all period levels
3. ✅ **Browser cache masking problems** — Added cache-busting `?v=` timestamp to fetch calls
4. ✅ **Period-level day-of-week** — Created `extract_period_day_of_week_analysis()` at all levels
5. ✅ **Quarterly time ranges** — Q3: 13:00-15:00, Q4: 15:00-16:00 (was overlapping)
6. ✅ **Day-of-week metrics** — Changed from win% to dollar P&L display
7. ✅ **Hourly UI redesign** — Replaced two Plotly charts with clean card-based layout
8. ✅ **Anomaly hour data key** — Fixed from '09:30' to '09:00' for correct data retrieval
9. ✅ **Period-level filtering** — Added hourly and trading quarter analysis at week/month/quarter/year levels

### Current Implementation Status
- ✅ **Overview Tab** — Fully functional with all metrics
- ✅ **Ladder Analysis Tab** — Complete with all ladder breakdowns
- ✅ **Entry Setup Tab** — Full setup type analysis
- ✅ **Time & Day Patterns Tab** — Period-aware with individual hourly cards
- 🟡 **Risk & Reward Tab** — Placeholder (Coming Soon)
- 🟡 **Trade Analysis Tab** — Placeholder (Coming Soon)

---

## Data Flow

```
Excel (NQ/MNQ)     TradingView CSV (ES/MES)
       ↓                     ↓
   Pandas Load          Pandas Load
       ↓                     ↓
   Parse Trades → extract_ladder_analysis()
   Parse Trades → extract_period_setup_type_analysis()
   Parse Trades → extract_period_day_of_week_analysis() ← **All period levels**
   Parse Trades → extract_period_hourly_analysis() ← **All period levels** (new)
   Parse Trades → extract_period_trading_quarter_analysis() ← **All period levels** (new)
       ↓
   Aggregate by Period (Year → Q → M → W → D)
   Generate 3 trade-type variants at each level
       ↓
   dashboard_data.json (8.1MB hierarchical JSON)
       ↓
   Frontend (HTML/JS) loads and renders
       ↓
   User applies period filters
   Dashboard displays period-specific metrics
```

---

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| **unified-dashboard.html** | ~/Desktop/ | Main UI and frontend logic |
| **update_dashboard_data.py** | SJ Work Vault/.../report-downloads/ | Data generation backend |
| **dashboard_data.json** | ~/Desktop/ | Generated hierarchical data (8.1MB) |
| **GitHub Repo** | sbjtrades/new-strategy-reports | Remote source control |

---

## Key Metrics Tracked

- **Trades** — Total entry trades
- **Wins/Losses** — Count of winning and losing trades
- **Win %** — Percentage of trades that were winners
- **Net P&L** — Total profit/loss in dollars
- **Avg P&L** — Average profit/loss per trade
- **Gross Profit/Loss** — Sum of all winners / sum of all losers
- **Avg Win/Loss** — Average dollar amount won or lost per winning/losing trade
- **Point Value** — Total points for directional analysis

---

## Next Steps (Pending)

1. **Daily Filtering** (user stated: "next filter is going to be daily")
   - Add daily-level filter dropdown
   - Create `extract_period_daily_analysis()` function
   - Integrate daily data at day level within weeks

2. **Risk & Reward Tab**
   - P&L bucket analysis
   - Risk/reward ratio distributions
   - Correlation analysis

3. **Trade Analysis Tab**
   - Individual trade review
   - Entry/exit analysis
   - Ladder transition tracking

---

## Dev Notes for Tomorrow

- **Python Backend**: `/venv/bin/python update_dashboard_data.py` to regenerate data
- **Frontend Server**: `python3 -m http.server 8001` from ~/Desktop/
- **Cache Busting**: Always use `?v=` + timestamp for fresh data loads
- **Period Data**: Use `getPeriodLevelData(instrumentData, 'by_hour')` helper for flexible retrieval
- **GitHub**: All changes pushed to `sbjtrades/new-strategy-reports` main branch

---

**Last Updated**: 2026-04-26 22:18:58  
**Status**: Period-level filtering complete and tested ✅
