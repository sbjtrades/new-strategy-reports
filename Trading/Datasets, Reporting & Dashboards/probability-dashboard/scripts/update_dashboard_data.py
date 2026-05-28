#!/usr/bin/env python3
"""
Generate dashboard_data.json from latest NQ and ES backtest files.
Run weekly after downloading new data from TradingView.
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import glob
import re

# Paths
BASE_PATH = Path(__file__).parent
DATA_DIR = BASE_PATH.parent / "data"
NQ_DIR = DATA_DIR
ES_DIR = DATA_DIR
OUTPUT_FILE = DATA_DIR / "dashboard_data.json"

def find_latest_file(directory):
    """Find most recent master or comprehensive file, preferring master reports."""
    files = list(directory.glob("**/*.csv")) + list(directory.glob("**/*.xlsx"))
    if not files:
        return None
    
    # Prefer master files (they have "master" in the path or are larger)
    master_files = [f for f in files if 'master' in f.name.lower() or 'master' in str(f).lower()]
    if master_files:
        return max(master_files, key=lambda p: p.stat().st_mtime)
    
    # Fall back to any file, preferring larger ones (more data)
    return max(files, key=lambda p: p.stat().st_size)
def load_data(filepath):
    """Load CSV or XLSX file."""
    if filepath.suffix.lower() == '.csv':
        return pd.read_csv(filepath)
    else:
        # Try to read "List of trades" sheet, fall back to first sheet
        try:
            return pd.read_excel(filepath, sheet_name='List of trades')
        except:
            return pd.read_excel(filepath)

def extract_metrics(df):
    """Extract key metrics from trade data."""
    if df.empty:
        return {}
    
    # Ensure date column exists (try common names)
    date_col = None
    for col in ['Date', 'date', 'Entry Date', 'entry_date', 'open_time']:
        if col in df.columns:
            date_col = col
            break
    
    if not date_col:
        return {}
    
    df['date'] = pd.to_datetime(df[date_col])
    
    # Extract profit/loss column
    pnl_col = None
    for col in ['P&L', 'pnl', 'profit', 'Profit', 'PnL', 'net_profit']:
        if col in df.columns:
            pnl_col = col
            break
    
    pnl = df[pnl_col].sum() if pnl_col else 0
    
    # Extract wins/losses
    wins = len(df[df[pnl_col] > 0]) if pnl_col else 0
    losses = len(df[df[pnl_col] <= 0]) if pnl_col else 0
    total_trades = len(df)
    
    return {
        'trades': int(total_trades),
        'wins': int(wins),
        'losses': int(losses),
        'win_pct': round((wins / total_trades * 100) if total_trades > 0 else 0, 1),
        'pnl': round(pnl, 2),
        'avg_trade': round(pnl / total_trades if total_trades > 0 else 0, 2),
        'start_date': df['date'].min().strftime('%Y-%m-%d'),
        'end_date': df['date'].max().strftime('%Y-%m-%d'),
    }

def extract_ladder_analysis(df, pnl_col):
    """Extract ladder and setup type analysis from trades.
    
    Counts ALL trades including primary transitions and reversals:
    - Longs: Entry long on UP ladders (ORH, UL1-UL10) only
    - Shorts: Entry short on DOWN ladders (ORL, DL1-DL10) only
    - INCLUDES: Reversal trades (e.g., Reversal Short on UP ladders)
    
    For ORH/ORL: counts trades where FROM ladder is ORH/ORL
    """
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    # Filter for entry trades only
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}
    
    # Parse ladder from signal
    entries['from_ladder'] = None
    entries['to_ladder'] = None
    entries['direction'] = None
    
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        entry_type = str(entries.loc[idx, 'Type']).lower()
        
        # Determine direction from Type column
        if 'entry long' in entry_type:
            direction = 'Long'
        elif 'entry short' in entry_type:
            direction = 'Short'
        else:
            direction = 'Unknown'
        
        # Extract FROM and TO ladders from arrow transition
        from_ladder = None
        to_ladder = None
        
        if '→' in signal_str:
            parts = signal_str.split('→')
            # Extract FROM ladder (before arrow)
            from_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[0])
            if from_match:
                from_ladder = from_match.group(1)
            
            # Extract TO ladder (after arrow)
            to_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[1])
            if to_match:
                to_ladder = to_match.group(1)
        
        # Include ALL trades (primary + reversals) as long as we have a from_ladder
        # Examples:
        # - Longs on UP ladders (ORH, UL*) = primary
        # - Shorts on DOWN ladders (ORL, DL*) = primary  
        # - Shorts on UP ladders (UL*) = reversal short (exit from rally)
        # - Longs on DOWN ladders (DL*) = reversal long (exit from drop)
        if from_ladder:
            entries.at[idx, 'from_ladder'] = from_ladder
            entries.at[idx, 'to_ladder'] = to_ladder
            entries.at[idx, 'direction'] = direction
    
    # Keep all entries (remove NaN only)
    entries = entries.dropna(subset=['from_ladder'])
    
    if entries.empty:
        return {}
    
    # Build ladder analysis using FROM ladder
    ladder_data = {}
    
    # Get all unique ladders, sorted
    ladders = sorted(entries['from_ladder'].unique(), key=lambda x: (
        # Custom sort: ORH first, then UL in numerical order, then ORL, then DL in numerical order
        (0, 0) if x == 'ORH' else
        (1, int(x[2:])) if x.startswith('UL') else
        (2, 0) if x == 'ORL' else
        (3, int(x[2:])) if x.startswith('DL') else
        (4, x)
    ))
    
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    
    for ladder in ladders:
        ladder_trades = entries[entries['from_ladder'] == ladder]
        ladder_data[ladder] = {}
        
        # Only split by direction - each ladder should only have one direction
        for direction in ['Long', 'Short']:
            dir_trades = ladder_trades[ladder_trades['direction'] == direction]
            if dir_trades.empty:
                continue
            
            if pnl_col_final:
                win_mask = dir_trades[pnl_col_final] > 0
                wins = int(win_mask.sum())
                total = len(dir_trades)
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
                pnl = round(dir_trades[pnl_col_final].sum(), 2)
                
                wins_df = dir_trades[win_mask]
                losses_df = dir_trades[~win_mask]
                gross_profit = round(wins_df[pnl_col_final].sum(), 2)
                gross_loss = round(losses_df[pnl_col_final].sum(), 2)
                avg_win = round(wins_df[pnl_col_final].mean(), 2) if not wins_df.empty else 0
                avg_loss = round(losses_df[pnl_col_final].mean(), 2) if not losses_df.empty else 0
                profit_factor = round(abs(gross_profit / gross_loss), 2) if gross_loss != 0 else 0
                rr_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0
                expectancy = round((win_pct/100 * avg_win) + ((1 - win_pct/100) * avg_loss), 2)
                
                mfe_col = next((c for c in dir_trades.columns if 'favorable excursion' in c.lower() and 'usd' in c.lower()), None)
                mae_col = next((c for c in dir_trades.columns if 'adverse excursion' in c.lower() and 'usd' in c.lower()), None)
                avg_mfe_wins = round(wins_df[mfe_col].mean(), 2) if (mfe_col and not wins_df.empty) else 0
                avg_mae_losses = round(losses_df[mae_col].mean(), 2) if (mae_col and not losses_df.empty) else 0
                mfe_capture = round((avg_win / avg_mfe_wins * 100), 1) if (avg_mfe_wins and avg_mfe_wins > 0) else 0
            else:
                wins = 0
                total = len(dir_trades)
                win_pct = 0
                pnl = gross_profit = gross_loss = avg_win = avg_loss = 0
                profit_factor = rr_ratio = expectancy = avg_mfe_wins = avg_mae_losses = mfe_capture = 0
            
            ladder_data[ladder][direction] = {
                'trades': int(total),
                'wins': int(wins),
                'losses': int(total - wins),
                'win_pct': win_pct,
                'pnl': pnl,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'rr_ratio': rr_ratio,
                'expectancy': expectancy,
                'avg_mfe_wins': avg_mfe_wins,
                'avg_mae_losses': avg_mae_losses,
                'mfe_capture_pct': mfe_capture,
            }
    
    return ladder_data

def extract_directional_ladder_analysis(df, pnl_col):
    """Extract ladder analysis for DIRECTIONAL trades ONLY.
    
    Includes only:
    - Longs on UP ladders (ORH, UL*)
    - Shorts on DOWN ladders (ORL, DL*)
    
    Excludes reversals:
    - Shorts on UP ladders (Reversal Short)
    - Longs on DOWN ladders (Reversal Long)
    """
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    # Filter for entry trades only
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}
    
    # Parse ladder from signal
    entries['from_ladder'] = None
    entries['to_ladder'] = None
    entries['direction'] = None
    
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        entry_type = str(entries.loc[idx, 'Type']).lower()
        
        if 'entry long' in entry_type:
            direction = 'Long'
        elif 'entry short' in entry_type:
            direction = 'Short'
        else:
            direction = 'Unknown'
        
        if '→' in signal_str:
            parts = signal_str.split('→')
            from_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[0])
            if from_match:
                from_ladder = from_match.group(1)
            else:
                continue
            
            to_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[1])
            if to_match:
                to_ladder = to_match.group(1)
            else:
                to_ladder = None
            
            # FILTER: Only keep directional trades
            # Long on UP ladders (ORH, UL*) = directional
            # Short on DOWN ladders (ORL, DL*) = directional
            is_directional = (
                (direction == 'Long' and (from_ladder == 'ORH' or from_ladder.startswith('UL'))) or
                (direction == 'Short' and (from_ladder == 'ORL' or from_ladder.startswith('DL')))
            )
            
            if is_directional and from_ladder:
                entries.at[idx, 'from_ladder'] = from_ladder
                entries.at[idx, 'to_ladder'] = to_ladder
                entries.at[idx, 'direction'] = direction
    
    entries = entries.dropna(subset=['from_ladder'])
    
    if entries.empty:
        return {}
    
    ladder_data = {}
    ladders = sorted(entries['from_ladder'].unique(), key=lambda x: (
        (0, 0) if x == 'ORH' else
        (1, int(x[2:])) if x.startswith('UL') else
        (2, 0) if x == 'ORL' else
        (3, int(x[2:])) if x.startswith('DL') else
        (4, x)
    ))
    
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    
    for ladder in ladders:
        ladder_trades = entries[entries['from_ladder'] == ladder]
        ladder_data[ladder] = {}
        
        for direction in ['Long', 'Short']:
            dir_trades = ladder_trades[ladder_trades['direction'] == direction]
            if dir_trades.empty:
                continue
            
            if pnl_col_final:
                wins = len(dir_trades[dir_trades[pnl_col_final] > 0])
                total = len(dir_trades)
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
                pnl = round(dir_trades[pnl_col_final].sum(), 2)
            else:
                wins = 0
                total = len(dir_trades)
                win_pct = 0
                pnl = 0
            
            ladder_data[ladder][direction] = {
                'trades': int(total),
                'wins': int(wins),
                'losses': int(total - wins),
                'win_pct': win_pct,
                'pnl': pnl
            }
    
    return ladder_data

def extract_reversals_ladder_analysis(df, pnl_col):
    """Extract ladder analysis for REVERSAL trades ONLY.
    
    Includes only:
    - Shorts on UP ladders (Reversal Short)
    - Longs on DOWN ladders (Reversal Long)
    """
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    # Filter for entry trades only
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}
    
    # Parse ladder from signal
    entries['from_ladder'] = None
    entries['to_ladder'] = None
    entries['direction'] = None
    
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        entry_type = str(entries.loc[idx, 'Type']).lower()
        
        if 'entry long' in entry_type:
            direction = 'Long'
        elif 'entry short' in entry_type:
            direction = 'Short'
        else:
            direction = 'Unknown'
        
        if '→' in signal_str:
            parts = signal_str.split('→')
            from_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[0])
            if from_match:
                from_ladder = from_match.group(1)
            else:
                continue
            
            to_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[1])
            if to_match:
                to_ladder = to_match.group(1)
            else:
                to_ladder = None
            
            # FILTER: Only keep REVERSAL trades
            # Short on UP ladders (ORH, UL*) = Reversal Short
            # Long on DOWN ladders (ORL, DL*) = Reversal Long
            is_reversal = (
                (direction == 'Short' and (from_ladder == 'ORH' or from_ladder.startswith('UL'))) or
                (direction == 'Long' and (from_ladder == 'ORL' or from_ladder.startswith('DL')))
            )
            
            if is_reversal and from_ladder:
                entries.at[idx, 'from_ladder'] = from_ladder
                entries.at[idx, 'to_ladder'] = to_ladder
                entries.at[idx, 'direction'] = direction
    
    entries = entries.dropna(subset=['from_ladder'])
    
    if entries.empty:
        return {}
    
    ladder_data = {}
    ladders = sorted(entries['from_ladder'].unique(), key=lambda x: (
        (0, 0) if x == 'ORH' else
        (1, int(x[2:])) if x.startswith('UL') else
        (2, 0) if x == 'ORL' else
        (3, int(x[2:])) if x.startswith('DL') else
        (4, x)
    ))
    
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    
    for ladder in ladders:
        ladder_trades = entries[entries['from_ladder'] == ladder]
        ladder_data[ladder] = {}
        
        for direction in ['Long', 'Short']:
            dir_trades = ladder_trades[ladder_trades['direction'] == direction]
            if dir_trades.empty:
                continue
            
            if pnl_col_final:
                wins = len(dir_trades[dir_trades[pnl_col_final] > 0])
                total = len(dir_trades)
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
                pnl = round(dir_trades[pnl_col_final].sum(), 2)
            else:
                wins = 0
                total = len(dir_trades)
                win_pct = 0
                pnl = 0
            
            ladder_data[ladder][direction] = {
                'trades': int(total),
                'wins': int(wins),
                'losses': int(total - wins),
                'win_pct': win_pct,
                'pnl': pnl
            }
    
    return ladder_data

def extract_risk_reward_summary(df, pnl_col):
    """Compute overall and per-ladder R&R metrics including MFE/MAE."""
    if df.empty or 'Signal' not in df.columns:
        return {}

    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}

    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    if not pnl_col_final:
        return {}

    mfe_col = next((c for c in entries.columns if 'favorable excursion' in c.lower() and 'usd' in c.lower()), None)
    mae_col = next((c for c in entries.columns if 'adverse excursion' in c.lower() and 'usd' in c.lower()), None)

    # Parse ladder + direction
    entries['from_ladder'] = None
    entries['direction'] = None
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        entry_type = str(entries.loc[idx, 'Type']).lower()
        direction = 'Long' if 'entry long' in entry_type else ('Short' if 'entry short' in entry_type else None)
        if '→' in signal_str:
            from_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', signal_str.split('→')[0])
            if from_match:
                entries.at[idx, 'from_ladder'] = from_match.group(1)
        entries.at[idx, 'direction'] = direction

    entries = entries.dropna(subset=['from_ladder', 'direction'])

    def _metrics(subset):
        if subset.empty:
            return {}
        win_mask = subset[pnl_col_final] > 0
        wins_df = subset[win_mask]
        losses_df = subset[~win_mask]
        wins = int(win_mask.sum())
        total = len(subset)
        gross_profit = round(wins_df[pnl_col_final].sum(), 2)
        gross_loss = round(losses_df[pnl_col_final].sum(), 2)
        avg_win = round(wins_df[pnl_col_final].mean(), 2) if not wins_df.empty else 0
        avg_loss = round(losses_df[pnl_col_final].mean(), 2) if not losses_df.empty else 0
        win_pct = round(wins / total * 100, 1) if total > 0 else 0
        profit_factor = round(abs(gross_profit / gross_loss), 2) if gross_loss != 0 else 0
        rr_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0
        expectancy = round((win_pct/100 * avg_win) + ((1 - win_pct/100) * avg_loss), 2)
        avg_mfe_wins = round(wins_df[mfe_col].mean(), 2) if (mfe_col and not wins_df.empty) else 0
        avg_mae_losses = round(losses_df[mae_col].mean(), 2) if (mae_col and not losses_df.empty) else 0
        mfe_capture = round(avg_win / avg_mfe_wins * 100, 1) if avg_mfe_wins and avg_mfe_wins > 0 else 0
        return {
            'trades': total,
            'wins': wins,
            'losses': total - wins,
            'win_pct': win_pct,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'rr_ratio': rr_ratio,
            'expectancy': expectancy,
            'avg_mfe_wins': avg_mfe_wins,
            'avg_mae_losses': avg_mae_losses,
            'mfe_capture_pct': mfe_capture,
        }

    # Overall
    overall = _metrics(entries)

    # By direction
    longs = _metrics(entries[entries['direction'] == 'Long'])
    shorts = _metrics(entries[entries['direction'] == 'Short'])

    # By ladder
    ladders_sorted = sorted(entries['from_ladder'].unique(), key=lambda x: (
        (0, 0) if x == 'ORH' else
        (1, int(x[2:])) if x.startswith('UL') else
        (2, 0) if x == 'ORL' else
        (3, int(x[2:])) if x.startswith('DL') else
        (4, x)
    ))
    by_ladder = {}
    for ladder in ladders_sorted:
        lt = entries[entries['from_ladder'] == ladder]
        by_ladder[ladder] = {
            'overall': _metrics(lt),
            'Long': _metrics(lt[lt['direction'] == 'Long']),
            'Short': _metrics(lt[lt['direction'] == 'Short']),
        }

    return {
        'overall': overall,
        'longs': longs,
        'shorts': shorts,
        'by_ladder': by_ladder,
    }

def extract_trade_analysis(df, pnl_col):
    """Extract comprehensive trade analysis: streaks, duration, drawdown, daily P&L, longs/shorts."""
    if df.empty or 'Type' not in df.columns:
        return {}

    # Resolve PnL column
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    if not pnl_col_final:
        return {}

    date_col = 'Date and time'
    if date_col not in df.columns:
        date_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
    if not date_col:
        return {}

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    # ── ENTRY TRADES ONLY (for most metrics) ───────────────────────────────
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    exits = df[df['Type'].str.contains('Exit', na=False, case=False)].copy()

    # ── DURATION per trade (entry→exit pairing by Trade #) ─────────────────
    if 'Trade #' in df.columns:
        entry_times = df[df['Type'].str.contains('Entry', na=False)].set_index('Trade #')[date_col]
        exit_times  = df[df['Type'].str.contains('Exit',  na=False)].set_index('Trade #')[date_col]
        common = entry_times.index.intersection(exit_times.index)
        durations = ((exit_times.loc[common] - entry_times.loc[common]).dt.total_seconds() / 60.0).clip(lower=0)
        # Merge duration back onto entries
        entries = entries.set_index('Trade #').copy()
        entries['duration_min'] = durations
        entries = entries.reset_index()
    else:
        entries['duration_min'] = None

    # ── DIRECTION parsing ───────────────────────────────────────────────────
    entries['direction'] = entries['Type'].str.lower().apply(
        lambda t: 'Long' if 'long' in t else ('Short' if 'short' in t else None)
    )

    # ── PNL per entry ───────────────────────────────────────────────────────
    pnl_series = entries[pnl_col_final]
    win_mask = pnl_series > 0

    # ── STREAKS ─────────────────────────────────────────────────────────────
    def streak_stats(mask_series):
        max_streak = cur_streak = 0
        streaks = []
        for v in mask_series:
            if v:
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
            else:
                if cur_streak > 0:
                    streaks.append(cur_streak)
                cur_streak = 0
        if cur_streak > 0:
            streaks.append(cur_streak)
        avg = round(sum(streaks)/len(streaks), 1) if streaks else 0
        hist = {}
        for s in streaks:
            hist[str(s)] = hist.get(str(s), 0) + 1
        return max_streak, avg, hist

    max_win_streak, avg_win_streak, win_streak_hist = streak_stats(win_mask)
    max_loss_streak, avg_loss_streak, loss_streak_hist = streak_stats(~win_mask)

    # ── DURATION stats ──────────────────────────────────────────────────────
    dur = entries['duration_min'].dropna()
    dur_wins = entries.loc[win_mask, 'duration_min'].dropna()
    dur_losses = entries.loc[~win_mask, 'duration_min'].dropna()
    avg_win_dur = round(dur_wins.mean(), 1) if not dur_wins.empty else 0
    avg_loss_dur = round(dur_losses.mean(), 1) if not dur_losses.empty else 0

    # ── LARGEST WIN / LOSS ──────────────────────────────────────────────────
    largest_win = round(pnl_series.max(), 2) if not pnl_series.empty else 0
    largest_loss = round(pnl_series.min(), 2) if not pnl_series.empty else 0

    # ── DAILY P&L ───────────────────────────────────────────────────────────
    entries['trade_date'] = entries[date_col].dt.date
    daily_pnl_series = entries.groupby('trade_date')[pnl_col_final].sum()
    best_day = round(daily_pnl_series.max(), 2) if not daily_pnl_series.empty else 0
    worst_day = round(daily_pnl_series.min(), 2) if not daily_pnl_series.empty else 0
    best_day_date = str(daily_pnl_series.idxmax()) if not daily_pnl_series.empty else ''
    worst_day_date = str(daily_pnl_series.idxmin()) if not daily_pnl_series.empty else ''

    # Top/bottom 10 trading days
    sorted_days = daily_pnl_series.sort_values(ascending=False)
    top10 = [{'date': str(d), 'pnl': round(v, 2)} for d, v in sorted_days.head(10).items()]
    bottom10 = [{'date': str(d), 'pnl': round(v, 2)} for d, v in sorted_days.tail(10).sort_values().items()]

    # ── DRAWDOWN (peak-to-trough on CUMULATIVE P&L sorted by entry time) ────
    entries_sorted = entries.sort_values(date_col)
    cum_pnl = entries_sorted[pnl_col_final].cumsum()
    rolling_peak = cum_pnl.cummax()
    drawdown = cum_pnl - rolling_peak
    max_drawdown = round(drawdown.min(), 2)

    # Build drawdown curve as daily aggregation (for chart)
    entries_sorted['cum_pnl'] = cum_pnl.values
    entries_sorted['drawdown'] = drawdown.values
    entries_sorted['trade_date'] = entries_sorted[date_col].dt.date

    # Daily cumulative P&L (end-of-day) + daily drawdown (worst of day)
    daily_curve = entries_sorted.groupby('trade_date').agg(
        daily_pnl=(pnl_col_final, 'sum'),
        end_cum_pnl=('cum_pnl', 'last'),
        min_drawdown=('drawdown', 'min')
    ).reset_index()
    daily_curve['trade_date'] = daily_curve['trade_date'].astype(str)

    # Recovery stats (avg trades to return to peak after drawdown)
    in_drawdown = False
    recovery_trades = []
    dd_count = 0
    for is_dd in (drawdown < 0).values:
        if is_dd:
            in_drawdown = True
            dd_count += 1
        elif in_drawdown:
            recovery_trades.append(dd_count)
            in_drawdown = False
            dd_count = 0
    avg_recovery = round(sum(recovery_trades)/len(recovery_trades), 0) if recovery_trades else 0

    # ── LONGS vs SHORTS breakdown ───────────────────────────────────────────
    def dir_stats(mask):
        sub = entries[mask]
        if sub.empty:
            return {}
        wins_s = sub[pnl_col_final] > 0
        gp = round(sub.loc[wins_s, pnl_col_final].sum(), 2)
        gl = round(sub.loc[~wins_s, pnl_col_final].sum(), 2)
        t = len(sub)
        w = int(wins_s.sum())
        return {
            'trades': t,
            'wins': w,
            'losses': t - w,
            'win_pct': round(w/t*100, 1) if t > 0 else 0,
            'total_pnl': round(sub[pnl_col_final].sum(), 2),
            'gross_wins': gp,
            'gross_losses': gl,
            'avg_pnl_per_trade': round(sub[pnl_col_final].sum()/t, 2) if t > 0 else 0,
        }

    longs_stats = dir_stats(entries['direction'] == 'Long')
    shorts_stats = dir_stats(entries['direction'] == 'Short')

    # ── P&L DISTRIBUTION arrays (for box plots) ────────────────────────────
    win_pnls = [round(v, 2) for v in entries.loc[win_mask, pnl_col_final].tolist()]
    loss_pnls = [round(v, 2) for v in entries.loc[~win_mask, pnl_col_final].tolist()]
    win_durs = [round(v, 1) for v in dur_wins.tolist()]
    loss_durs = [round(v, 1) for v in dur_losses.tolist()]

    # ── DURATION BY LADDER ──────────────────────────────────────────────────
    def parse_from_ladder(signal_str):
        if '→' in str(signal_str):
            m = re.search(r'(UL\d+|DL\d+|ORL|ORH)', str(signal_str).split('→')[0])
            return m.group(1) if m else None
        return None

    if 'Signal' in entries.columns:
        entries['from_ladder'] = entries['Signal'].apply(parse_from_ladder)
        dur_by_ladder = {}
        for ldr, grp in entries.dropna(subset=['from_ladder']).groupby('from_ladder'):
            w_grp = grp[grp[pnl_col_final] > 0]
            l_grp = grp[grp[pnl_col_final] <= 0]
            dur_by_ladder[ldr] = {
                'avg_win_dur': round(w_grp['duration_min'].mean(), 1) if not w_grp['duration_min'].dropna().empty else 0,
                'avg_loss_dur': round(l_grp['duration_min'].mean(), 1) if not l_grp['duration_min'].dropna().empty else 0,
            }
    else:
        dur_by_ladder = {}

    # ── CONSECUTIVE LOSS RISK BY LADDER (per-rung isolated) ────────────────
    consec_loss_by_ladder = {}
    if 'from_ladder' in entries.columns:
        for ldr, grp in entries.dropna(subset=['from_ladder']).groupby('from_ladder'):
            grp_sorted = grp.sort_values(date_col)
            max_cl, cur_cl = 0, 0
            for v in (grp_sorted[pnl_col_final] <= 0).values:
                if v:
                    cur_cl += 1
                    max_cl = max(max_cl, cur_cl)
                else:
                    cur_cl = 0
            consec_loss_by_ladder[ldr] = int(max_cl)

    # ── CONSECUTIVE LOSS RISK BY SETUP ─────────────────────────────────────
    consec_loss_by_setup = {}
    if 'Signal' in entries.columns:
        def parse_setup(signal_str, entry_type):
            s = str(signal_str)
            t = str(entry_type).lower()
            if 'reversal short' in s.lower() or ('short' in t and ('ul' in s.lower() or 'orh' in s.lower())):
                return 'Reversal Short'
            if 'reversal long' in s.lower() or ('long' in t and ('dl' in s.lower() or 'orl' in s.lower())):
                return 'Reversal Long'
            if 'entry long' in t:
                return 'Bull Setup'
            if 'entry short' in t:
                return 'Short Setup'
            return 'Unknown'

        entries['setup_type'] = entries.apply(lambda r: parse_setup(r['Signal'], r['Type']), axis=1)
        for setup, grp in entries.groupby('setup_type'):
            if setup == 'Unknown':
                continue
            grp_sorted = grp.sort_values(date_col)
            max_cl, cur_cl = 0, 0
            for v in (grp_sorted[pnl_col_final] <= 0).values:
                if v:
                    cur_cl += 1
                    max_cl = max(max_cl, cur_cl)
                else:
                    cur_cl = 0
            consec_loss_by_setup[setup] = int(max_cl)

    # UL vs DL isolated for setup
    consec_loss_setup_ul = {}
    consec_loss_setup_dl = {}
    if 'setup_type' in entries.columns and 'from_ladder' in entries.columns:
        for setup, grp in entries.groupby('setup_type'):
            if setup == 'Unknown':
                continue
            ul_grp = grp[grp['from_ladder'].str.startswith('U', na=False) | (grp['from_ladder'] == 'ORH')].sort_values(date_col)
            dl_grp = grp[grp['from_ladder'].str.startswith('D', na=False) | (grp['from_ladder'] == 'ORL')].sort_values(date_col)
            def max_consec_loss(sub):
                mx, cur = 0, 0
                for v in (sub[pnl_col_final] <= 0).values:
                    if v: cur += 1; mx = max(mx, cur)
                    else: cur = 0
                return int(mx)
            consec_loss_setup_ul[setup] = max_consec_loss(ul_grp) if not ul_grp.empty else 0
            consec_loss_setup_dl[setup] = max_consec_loss(dl_grp) if not dl_grp.empty else 0

    return {
        'max_win_streak': int(max_win_streak),
        'max_loss_streak': int(max_loss_streak),
        'avg_win_streak': avg_win_streak,
        'avg_loss_streak': avg_loss_streak,
        'avg_win_duration_min': avg_win_dur,
        'avg_loss_duration_min': avg_loss_dur,
        'largest_win': largest_win,
        'largest_loss': largest_loss,
        'best_day': best_day,
        'worst_day': worst_day,
        'best_day_date': best_day_date,
        'worst_day_date': worst_day_date,
        'max_drawdown': max_drawdown,
        'avg_recovery_trades': int(avg_recovery),
        'longs': longs_stats,
        'shorts': shorts_stats,
        'win_streak_histogram': win_streak_hist,
        'loss_streak_histogram': loss_streak_hist,
        'win_pnl_distribution': win_pnls[:5000],   # cap for JSON size
        'loss_pnl_distribution': loss_pnls[:5000],
        'win_duration_distribution': win_durs[:5000],
        'loss_duration_distribution': loss_durs[:5000],
        'daily_curve': daily_curve.to_dict(orient='records'),
        'duration_by_ladder': dur_by_ladder,
        'consec_loss_by_ladder': consec_loss_by_ladder,
        'consec_loss_by_setup': consec_loss_by_setup,
        'consec_loss_setup_ul': consec_loss_setup_ul,
        'consec_loss_setup_dl': consec_loss_setup_dl,
        'top10_days': top10,
        'bottom10_days': bottom10,
    }

def extract_setup_type_analysis(df, pnl_col):
    """Extract setup type analysis with ladder breakdown."""
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    # Filter for entry trades only
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}
    
    # Parse setup type and ladder from signal
    entries['ladder'] = None
    entries['setup_type'] = None
    
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        
        # Extract setup type
        if 'Reversal Short' in signal_str or ('RS' in signal_str.split()[0] if signal_str.split() else False):
            setup = 'Reversal Short'
        elif 'Reversal Long' in signal_str or ('RL' in signal_str.split()[0] if signal_str.split() else False):
            setup = 'Reversal Long'
        elif signal_str.startswith('SS'):
            setup = 'Short Setup'
        elif signal_str.startswith('BS'):
            setup = 'Buy Setup'
        else:
            setup = 'Other'
        
        # Extract ladder
        ladder_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', signal_str)
        ladder = ladder_match.group(1) if ladder_match else 'Unknown'
        
        entries.at[idx, 'setup_type'] = setup
        entries.at[idx, 'ladder'] = ladder
    
    # Get PnL column
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    
    # Overall setup type stats
    setup_stats = {}
    for setup_type in entries['setup_type'].unique():
        setup_trades = entries[entries['setup_type'] == setup_type]
        
        if pnl_col_final:
            wins = len(setup_trades[setup_trades[pnl_col_final] > 0])
            total = len(setup_trades)
            win_pct = round((wins / total * 100) if total > 0 else 0, 1)
            pnl = round(setup_trades[pnl_col_final].sum(), 2)
        else:
            wins = total = 0
            win_pct = 0
            pnl = 0
        
        setup_stats[setup_type] = {
            'trades': int(total),
            'wins': int(wins),
            'losses': int(total - wins),
            'win_pct': win_pct,
            'pnl': pnl
        }
    
    # Setup type by ladder
    ladder_setup_stats = {}
    
    # Up ladders (UL + ORL)
    up_ladders = entries[entries['ladder'].isin(['ORL', 'UL1', 'UL2', 'UL3', 'UL4', 'UL5', 'UL6', 'UL7', 'UL8', 'UL9', 'UL10'])]
    ladder_setup_stats['up_ladders'] = {}
    for ladder in sorted(up_ladders['ladder'].unique()):
        ladder_setup_stats['up_ladders'][ladder] = {}
        for setup_type in up_ladders['setup_type'].unique():
            trades = up_ladders[(up_ladders['ladder'] == ladder) & (up_ladders['setup_type'] == setup_type)]
            if trades.empty:
                continue
            
            if pnl_col_final:
                wins = len(trades[trades[pnl_col_final] > 0])
                total = len(trades)
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
            else:
                wins = total = 0
                win_pct = 0
            
            ladder_setup_stats['up_ladders'][ladder][setup_type] = {
                'trades': int(total),
                'wins': int(wins),
                'win_pct': win_pct
            }
    
    # Down ladders (DL + ORH)
    down_ladders = entries[entries['ladder'].isin(['ORH', 'DL1', 'DL2', 'DL3', 'DL4', 'DL5', 'DL6', 'DL7', 'DL8', 'DL9', 'DL10'])]
    ladder_setup_stats['down_ladders'] = {}
    for ladder in sorted(down_ladders['ladder'].unique()):
        ladder_setup_stats['down_ladders'][ladder] = {}
        for setup_type in down_ladders['setup_type'].unique():
            trades = down_ladders[(down_ladders['ladder'] == ladder) & (down_ladders['setup_type'] == setup_type)]
            if trades.empty:
                continue
            
            if pnl_col_final:
                wins = len(trades[trades[pnl_col_final] > 0])
                total = len(trades)
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
            else:
                wins = total = 0
                win_pct = 0
            
            ladder_setup_stats['down_ladders'][ladder][setup_type] = {
                'trades': int(total),
                'wins': int(wins),
                'win_pct': win_pct
            }
    
    return {
        'overall': setup_stats,
        'by_ladder': ladder_setup_stats
    }

def extract_setup_type_by_entry_ladder_with_pnl(df, pnl_col):
    """Extract setup type analysis by ENTRY ladder with P&L metrics.
    
    This shows:
    - Win % and trade count for each (entry_ladder + setup_type) combo
    - Total P&L and average P&L per trade
    - Grouped by entry point to identify profitable setup/ladder combos
    """
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    # Build trade pairs (Entry + Exit) by Trade #
    if 'Trade #' not in df.columns:
        return {}
    
    # Separate entry and exit rows
    entries_df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    exits_df = df[df['Type'].str.contains('Exit', na=False, case=False)].copy()
    
    if entries_df.empty or exits_df.empty:
        return {}
    
    # Get PnL column
    pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
    if pnl_col_final not in df.columns:
        pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
        pnl_col_final = pnl_cols[0] if pnl_cols else None
    
    # Merge entry and exit by Trade #
    trade_pairs = exits_df[['Trade #', pnl_col_final]].copy() if pnl_col_final else exits_df[['Trade #']].copy()
    trade_pairs = trade_pairs.rename(columns={pnl_col_final: 'pnl'} if pnl_col_final else {})
    
    # Get entry details (setup type, entry ladder)
    entries_detail = entries_df[['Trade #', 'Signal', 'Type']].copy()
    
    # Parse setup type and entry ladder from signal
    entries_detail['setup_type'] = None
    entries_detail['entry_ladder'] = None
    
    for idx, signal in entries_detail['Signal'].items():
        signal_str = str(signal)
        
        # Extract setup type from prefix
        if signal_str.startswith('BS'):
            setup = 'Bull Setup'
        elif signal_str.startswith('RL'):
            setup = 'Reversal Long'
        elif signal_str.startswith('RS'):
            setup = 'Reversal Short'
        elif signal_str.startswith('SS'):
            setup = 'Short Setup'
        else:
            setup = 'Other'
        
        # Extract entry ladder (FROM ladder, before arrow)
        parts = signal_str.split('→')
        if len(parts) >= 1:
            from_match = re.search(r'(ORH|ORL|UL\d+|DL\d+)', parts[0])
            entry_ladder = from_match.group(1) if from_match else 'Unknown'
        else:
            entry_ladder = 'Unknown'
        
        entries_detail.at[idx, 'setup_type'] = setup
        entries_detail.at[idx, 'entry_ladder'] = entry_ladder
    
    # Merge on Trade #
    combined = entries_detail.merge(
        trade_pairs, 
        on='Trade #', 
        how='inner'
    )
    
    if combined.empty:
        return {}
    
    # Group by setup type and entry ladder
    result = {}
    
    for setup_type in combined['setup_type'].unique():
        setup_trades = combined[combined['setup_type'] == setup_type]
        result[setup_type] = {}
        
        for entry_ladder in setup_trades['entry_ladder'].unique():
            ladder_trades = setup_trades[setup_trades['entry_ladder'] == entry_ladder]
            
            if pnl_col_final:
                wins = len(ladder_trades[ladder_trades['pnl'] > 0])
                total = len(ladder_trades)
                losses = total - wins
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
                total_pnl = round(ladder_trades['pnl'].sum(), 2)
                avg_pnl = round(ladder_trades['pnl'].mean(), 2)
                
                # Calculate gross profit and gross loss
                winning_trades = ladder_trades[ladder_trades['pnl'] > 0]
                losing_trades = ladder_trades[ladder_trades['pnl'] <= 0]
                gross_profit = round(winning_trades['pnl'].sum(), 2) if not winning_trades.empty else 0
                gross_loss = round(abs(losing_trades['pnl'].sum()), 2) if not losing_trades.empty else 0
            else:
                wins = total = losses = 0
                win_pct = total_pnl = avg_pnl = gross_profit = gross_loss = 0
            
            result[setup_type][entry_ladder] = {
                'trades': int(total),
                'wins': int(wins),
                'losses': int(losses),
                'win_pct': win_pct,
                'pnl_total': total_pnl,
                'pnl_avg': avg_pnl,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss
            }
    
    # Sort by setup type, then by entry ladder
    setup_order = ['Bull Setup', 'Reversal Long', 'Reversal Short', 'Short Setup', 'Other']
    result = {k: result[k] for k in setup_order if k in result}
    
    return result

def extract_period_setup_type_analysis(df, pnl_col):
    """Extract setup type analysis for a specific period (subset of trades).
    
    Returns same structure as extract_setup_type_by_entry_ladder_with_pnl
    but for just this period's trades.
    
    NOTE: This function works with Entry-only data (pre-filtered by aggregate_by_period).
    It pairs Entry and Exit rows by Trade # to get PnL data.
    """
    if df.empty or 'Signal' not in df.columns:
        return {}
    
    if 'Trade #' not in df.columns:
        return {}
    
    # Check if we have both Entry and Exit rows
    entries_df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    exits_df = df[df['Type'].str.contains('Exit', na=False, case=False)].copy()
    
    if entries_df.empty:
        return {}
    
    # If no exits, just use Entry trades as-is (for period-filtered data)
    if exits_df.empty:
        pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
        if pnl_col_final not in df.columns:
            pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
            pnl_col_final = pnl_cols[0] if pnl_cols else None
        
        # Use Entry rows directly with their PnL
        combined = entries_df[['Trade #', 'Signal', 'Type']].copy()
        if pnl_col_final and pnl_col_final in entries_df.columns:
            combined['pnl'] = entries_df[pnl_col_final]
        else:
            combined['pnl'] = 0
    else:
        # Standard path: pair Entry and Exit rows
        pnl_col_final = pnl_col if pnl_col in df.columns else 'Net P&L USD'
        if pnl_col_final not in df.columns:
            pnl_cols = [c for c in df.columns if 'P&L' in c or 'pnl' in c.lower()]
            pnl_col_final = pnl_cols[0] if pnl_cols else None
        
        trade_pairs = exits_df[['Trade #', pnl_col_final]].copy() if pnl_col_final else exits_df[['Trade #']].copy()
        trade_pairs = trade_pairs.rename(columns={pnl_col_final: 'pnl'} if pnl_col_final else {})
        
        entries_detail = entries_df[['Trade #', 'Signal', 'Type']].copy()
        combined = entries_detail.merge(trade_pairs, on='Trade #', how='inner')
    
    if combined.empty:
        return {}
    
    # Extract setup type and entry ladder from Signal
    combined['setup_type'] = None
    combined['entry_ladder'] = None
    
    for idx, signal in combined['Signal'].items():
        signal_str = str(signal)
        
        if signal_str.startswith('BS'):
            setup = 'Bull Setup'
        elif signal_str.startswith('RL'):
            setup = 'Reversal Long'
        elif signal_str.startswith('RS'):
            setup = 'Reversal Short'
        elif signal_str.startswith('SS'):
            setup = 'Short Setup'
        else:
            setup = 'Other'
        
        parts = signal_str.split('→')
        if len(parts) >= 1:
            from_match = re.search(r'(ORH|ORL|UL\d+|DL\d+)', parts[0])
            entry_ladder = from_match.group(1) if from_match else 'Unknown'
        else:
            entry_ladder = 'Unknown'
        
        combined.at[idx, 'setup_type'] = setup
        combined.at[idx, 'entry_ladder'] = entry_ladder
    
    if combined.empty:
        return {}
    
    result = {}
    for setup_type in combined['setup_type'].unique():
        setup_trades = combined[combined['setup_type'] == setup_type]
        result[setup_type] = {}
        
        for entry_ladder in setup_trades['entry_ladder'].unique():
            ladder_trades = setup_trades[setup_trades['entry_ladder'] == entry_ladder]
            
            if pnl_col_final:
                wins = len(ladder_trades[ladder_trades['pnl'] > 0])
                total = len(ladder_trades)
                losses = total - wins
                win_pct = round((wins / total * 100) if total > 0 else 0, 1)
                total_pnl = round(ladder_trades['pnl'].sum(), 2)
                avg_pnl = round(ladder_trades['pnl'].mean(), 2)
                winning_trades = ladder_trades[ladder_trades['pnl'] > 0]
                losing_trades = ladder_trades[ladder_trades['pnl'] <= 0]
                gross_profit = round(winning_trades['pnl'].sum(), 2) if not winning_trades.empty else 0
                gross_loss = round(abs(losing_trades['pnl'].sum()), 2) if not losing_trades.empty else 0
            else:
                wins = total = losses = 0
                win_pct = total_pnl = avg_pnl = gross_profit = gross_loss = 0
            
            result[setup_type][entry_ladder] = {
                'trades': int(total),
                'wins': int(wins),
                'losses': int(losses),
                'win_pct': win_pct,
                'pnl_total': total_pnl,
                'pnl_avg': avg_pnl,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss
            }
    
    setup_order = ['Bull Setup', 'Reversal Long', 'Reversal Short', 'Short Setup', 'Other']
    result = {k: result[k] for k in setup_order if k in result}
    
    return result

def calculate_trade_breakdown(df):
    """Calculate breakdown of trades into primary direction vs reversals.
    
    Returns:
    {
        'total_trades': int,
        'primary_direction': {
            'long_on_up': int,  (Longs on ORH/UL*)
            'short_on_down': int,  (Shorts on ORL/DL*)
            'total': int
        },
        'reversals': {
            'short_on_up': int,  (Shorts on UL*)
            'long_on_down': int,  (Longs on DL*)
            'total': int
        }
    }
    """
    if df.empty or 'Signal' not in df.columns or 'Type' not in df.columns:
        return {}
    
    entries = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if entries.empty:
        return {}
    
    long_on_up = 0
    short_on_down = 0
    short_on_up = 0
    long_on_down = 0
    
    for idx, signal in entries['Signal'].items():
        signal_str = str(signal)
        entry_type = str(entries.loc[idx, 'Type']).lower()
        
        # Determine direction
        if 'entry long' in entry_type:
            direction = 'Long'
        elif 'entry short' in entry_type:
            direction = 'Short'
        else:
            continue
        
        # Extract FROM ladder
        from_ladder = None
        if '→' in signal_str:
            parts = signal_str.split('→')
            from_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)', parts[0])
            if from_match:
                from_ladder = from_match.group(1)
        
        if not from_ladder:
            continue
        
        # Classify as primary or reversal
        if direction == 'Long':
            if from_ladder == 'ORH' or from_ladder.startswith('UL'):
                long_on_up += 1  # Primary
            elif from_ladder == 'ORL' or from_ladder.startswith('DL'):
                long_on_down += 1  # Reversal
        elif direction == 'Short':
            if from_ladder == 'ORL' or from_ladder.startswith('DL'):
                short_on_down += 1  # Primary
            elif from_ladder == 'ORH' or from_ladder.startswith('UL'):
                short_on_up += 1  # Reversal
    
    total = long_on_up + short_on_down + short_on_up + long_on_down
    
    return {
        'total_trades': int(total),
        'primary_direction': {
            'long_on_up': int(long_on_up),
            'short_on_down': int(short_on_down),
            'total': int(long_on_up + short_on_down)
        },
        'reversals': {
            'short_on_up': int(short_on_up),
            'long_on_down': int(long_on_down),
            'total': int(short_on_up + long_on_down)
        }
    }

def extract_period_day_of_week_analysis(df, pnl_col):
    """Extract day-of-week analysis for a specific period.
    
    Works with period-level data (entry trades only).
    Returns: {day_name: {trades, wins, losses, win_pct, pnl, ...}, ...}
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Extract day of week
    df['day_of_week'] = df['datetime'].dt.day_name()
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Aggregate by day (Mon-Fri only)
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    day_data = {}
    
    for day in days_order:
        day_df = df[df['day_of_week'] == day]
        if day_df.empty:
            continue
        
        day_trades = len(day_df)
        day_wins = len(day_df[day_df['pnl_value'] > 0])
        day_pnl = day_df['pnl_value'].sum()
        
        day_data[day] = {
            'trades': int(day_trades),
            'wins': int(day_wins),
            'losses': int(day_trades - day_wins),
            'win_pct': round((day_wins / day_trades * 100) if day_trades > 0 else 0, 1),
            'pnl': round(day_pnl, 2),
        }
    
    return day_data

def extract_period_hourly_analysis(df, pnl_col):
    """Extract hourly analysis for a specific period.
    
    Works with period-level data (entry trades only).
    Returns: {'09:00': {trades, wins, losses, win_pct, pnl, wins_gross, losses_gross, point_value, avg_pts}, ...}
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Extract hour
    df['hour'] = df['datetime'].dt.hour
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Look for Points column (common variations)
    point_col = None
    for col in ['Points', 'points', 'Pts', 'pts', 'Point Value', 'point_value']:
        if col in df.columns:
            point_col = col
            break
    
    if point_col:
        df['point_value'] = pd.to_numeric(df[point_col], errors='coerce').fillna(0)
    else:
        df['point_value'] = 0
    
    # Aggregate by hour (9-16 for trading hours 9:30am-4:00pm)
    hourly_data = {}
    
    for hour in sorted(df['hour'].unique()):
        if hour < 9 or hour > 16:
            continue  # Skip pre/post market
        
        hour_df = df[df['hour'] == hour]
        hour_trades = len(hour_df)
        hour_wins = len(hour_df[hour_df['pnl_value'] > 0])
        hour_pnl = hour_df['pnl_value'].sum()
        
        # Gross profit/loss
        wins_df = hour_df[hour_df['pnl_value'] > 0]
        losses_df = hour_df[hour_df['pnl_value'] <= 0]
        gross_profit = wins_df['pnl_value'].sum() if not wins_df.empty else 0
        gross_loss = losses_df['pnl_value'].sum() if not losses_df.empty else 0
        
        # Points
        total_pts = hour_df['point_value'].sum() if point_col else 0
        avg_pts = (total_pts / hour_trades) if hour_trades > 0 else 0
        
        hourly_data[f"{hour:02d}:00"] = {
            'trades': int(hour_trades),
            'wins': int(hour_wins),
            'losses': int(hour_trades - hour_wins),
            'win_pct': round((hour_wins / hour_trades * 100) if hour_trades > 0 else 0, 1),
            'pnl': round(hour_pnl, 2),
            'wins_gross': round(gross_profit, 2),
            'losses_gross': round(gross_loss, 2),
            'point_value': round(total_pts, 1),
            'avg_pts': round(avg_pts, 1),
        }
    
    return hourly_data

def extract_period_trading_quarter_analysis(df, pnl_col):
    """Extract trading quarter analysis for a specific period.
    
    Works with period-level data (entry trades only).
    Returns: {'Q1 (09:30-11:30) Opening': {trades, wins, losses, win_pct, pnl}, ...}
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Determine trading quarter for each trade
    def get_trading_quarter(dt):
        hour = dt.hour
        minute = dt.minute
        total_minutes = hour * 60 + minute
        market_open = 9 * 60 + 30  # 570 = 9:30
        
        if total_minutes >= market_open and total_minutes < (11 * 60 + 30):
            return 'Q1 (09:30-11:30) Opening'
        elif total_minutes >= (11 * 60 + 30) and total_minutes < (13 * 60):
            return 'Q2 (11:30-13:00) Lunch Approach'
        elif total_minutes >= (13 * 60) and total_minutes < (15 * 60):
            return 'Q3 (13:00-15:00) Post-Lunch'
        elif total_minutes >= (15 * 60) and total_minutes < 16 * 60 + 60:
            return 'Q4 (15:00-16:00) Close'
        return None
    
    df['trading_quarter'] = df['datetime'].apply(get_trading_quarter)
    df = df[df['trading_quarter'].notna()]
    
    if df.empty:
        return {}
    
    # Look for Points column (common variations)
    point_col = None
    for col in ['Points', 'points', 'Pts', 'pts', 'Point Value', 'point_value']:
        if col in df.columns:
            point_col = col
            break
    
    if point_col:
        df['point_value'] = pd.to_numeric(df[point_col], errors='coerce').fillna(0)
    else:
        df['point_value'] = 0
    
    # Aggregate by trading quarter
    quarter_data = {}
    
    for quarter in ['Q1 (09:30-11:30) Opening', 'Q2 (11:30-13:00) Lunch Approach', 'Q3 (13:00-15:00) Post-Lunch', 'Q4 (15:00-16:00) Close']:
        quarter_df = df[df['trading_quarter'] == quarter]
        if quarter_df.empty:
            continue
        
        quarter_trades = len(quarter_df)
        quarter_wins = len(quarter_df[quarter_df['pnl_value'] > 0])
        quarter_pnl = quarter_df['pnl_value'].sum()
        
        # Gross profit/loss
        wins_df = quarter_df[quarter_df['pnl_value'] > 0]
        losses_df = quarter_df[quarter_df['pnl_value'] <= 0]
        gross_profit = wins_df['pnl_value'].sum() if not wins_df.empty else 0
        gross_loss = losses_df['pnl_value'].sum() if not losses_df.empty else 0
        
        # Points
        total_pts = quarter_df['point_value'].sum() if point_col else 0
        avg_pts = (total_pts / quarter_trades) if quarter_trades > 0 else 0
        
        quarter_data[quarter] = {
            'trades': int(quarter_trades),
            'wins': int(quarter_wins),
            'losses': int(quarter_trades - quarter_wins),
            'win_pct': round((quarter_wins / quarter_trades * 100) if quarter_trades > 0 else 0, 1),
            'pnl': round(quarter_pnl, 2),
            'wins_gross': round(gross_profit, 2),
            'losses_gross': round(gross_loss, 2),
            'point_value': round(total_pts, 1),
            'avg_pts': round(avg_pts, 1),
        }
    
    return quarter_data

def aggregate_by_period(df, date_col, pnl_col):
    """Aggregate data by year, quarter, month, week.
    
    IMPORTANT: 
    - Only counts ENTRY trades (filters out exits to avoid doubling)
    - Ladder analysis: Only counts PRIMARY transitions (excludes reversals)
    - Setup analysis: INCLUDES all setups (Bull, Reversal Short, Short, Reversal Long)
    - Also generates setup_type_by_entry_ladder analysis at each period level
    """
    # Make a copy to avoid modifying original
    df = df.copy()
    
    # FILTER FOR ENTRY TRADES ONLY - this prevents doubling
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    
    # Convert date column
    df['date'] = pd.to_datetime(df[date_col], errors='coerce')
    
    # Remove rows with invalid dates
    df = df.dropna(subset=['date'])
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Extract year, quarter, month, week
    df['year'] = df['date'].dt.year
    df['quarter'] = df['date'].dt.quarter
    df['month'] = df['date'].dt.month
    df['week'] = df['date'].dt.isocalendar().week
    df['day'] = df['date'].dt.date

    # Direction for avg daily trade counts
    if 'Type' in df.columns:
        df['direction'] = df['Type'].str.lower().apply(
            lambda t: 'Long' if 'long' in t else ('Short' if 'short' in t else 'Unknown')
        )
    else:
        df['direction'] = 'Unknown'

    data_by_period = {}
    
    # By year
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        year_data = {}
        
        # By quarter
        for q in sorted(year_df['quarter'].unique()):
            q_df = year_df[year_df['quarter'] == q]
            q_data = {}
            
            # By month
            for month in sorted(q_df['month'].unique()):
                month_df = q_df[q_df['month'] == month]
                month_data = {}
                
                # By week
                for week in sorted(month_df['week'].unique()):
                    week_df = month_df[month_df['week'] == week]
                    week_day_data = {}
                    
                    # By day (within week)
                    for day in sorted(week_df['day'].unique()):
                        day_df = week_df[week_df['day'] == day]
                        day_trades = len(day_df)
                        day_wins = len(day_df[day_df['pnl_value'] > 0])
                        day_pnl = day_df['pnl_value'].sum()
                        
                        day_longs = len(day_df[day_df['direction'] == 'Long'])
                        day_shorts = len(day_df[day_df['direction'] == 'Short'])
                        week_day_data[str(day)] = {
                            'trades': int(day_trades),
                            'wins': int(day_wins),
                            'losses': int(day_trades - day_wins),
                            'win_pct': round((day_wins / day_trades * 100) if day_trades > 0 else 0, 1),
                            'pnl': round(day_pnl, 2),
                            'longs': int(day_longs),
                            'shorts': int(day_shorts),
                        }
                    
                    week_trades = len(week_df)
                    week_wins = len(week_df[week_df['pnl_value'] > 0])
                    week_pnl = week_df['pnl_value'].sum()
                    week_days = len(week_df['day'].unique())
                    week_avg_daily = round(week_trades / week_days, 1) if week_days > 0 else 0
                    week_avg_daily_longs = round(len(week_df[week_df['direction'] == 'Long']) / week_days, 1) if week_days > 0 else 0
                    week_avg_daily_shorts = round(len(week_df[week_df['direction'] == 'Short']) / week_days, 1) if week_days > 0 else 0
                    
                    # Generate ladder analysis for this week (all variants)
                    week_ladder = extract_ladder_analysis(week_df, pnl_col)
                    week_ladder_directional = extract_directional_ladder_analysis(week_df, pnl_col)
                    week_ladder_reversals = extract_reversals_ladder_analysis(week_df, pnl_col)
                    
                    # Generate setup analysis for this week
                    week_setup = extract_period_setup_type_analysis(week_df, pnl_col)
                    
                    # Generate day-of-week analysis for this week
                    week_day_of_week = extract_period_day_of_week_analysis(week_df, pnl_col)
                    
                    # Generate hourly analysis for this week
                    week_hourly = extract_period_hourly_analysis(week_df, pnl_col)
                    
                    # Generate trading quarter analysis for this week
                    week_trading_quarters = extract_period_trading_quarter_analysis(week_df, pnl_col)

                    # Generate candle position analysis for this week
                    week_candle_position = extract_hourly_candle_position_analysis(week_df, pnl_col)
                    
                    month_data[f"W{int(week)}"] = {
                        'trades': int(week_trades),
                        'wins': int(week_wins),
                        'losses': int(week_trades - week_wins),
                        'win_pct': round((week_wins / week_trades * 100) if week_trades > 0 else 0, 1),
                        'pnl': round(week_pnl, 2),
                        'avg_daily_total': week_avg_daily,
                        'avg_daily_longs': week_avg_daily_longs,
                        'avg_daily_shorts': week_avg_daily_shorts,
                        'by_day': week_day_data,
                        'by_day_of_week': week_day_of_week,
                        'by_hour': week_hourly,
                        'by_trading_quarter': week_trading_quarters,
                        'ladder_analysis': week_ladder,
                        'ladder_analysis_directional': week_ladder_directional,
                        'ladder_analysis_reversals': week_ladder_reversals,
                        'setup_type_by_entry_ladder': week_setup,
                        'candle_position_analysis': week_candle_position
                    }
                
                # Month summary
                month_trades = len(month_df)
                month_wins = len(month_df[month_df['pnl_value'] > 0])
                month_pnl = month_df['pnl_value'].sum()
                month_days = len(month_df['day'].unique())
                month_avg_daily = round(month_trades / month_days, 1) if month_days > 0 else 0
                month_avg_daily_longs = round(len(month_df[month_df['direction'] == 'Long']) / month_days, 1) if month_days > 0 else 0
                month_avg_daily_shorts = round(len(month_df[month_df['direction'] == 'Short']) / month_days, 1) if month_days > 0 else 0
                
                # Generate ladder analysis for this month (all variants)
                month_ladder = extract_ladder_analysis(month_df, pnl_col)
                month_ladder_directional = extract_directional_ladder_analysis(month_df, pnl_col)
                month_ladder_reversals = extract_reversals_ladder_analysis(month_df, pnl_col)
                
                # Generate setup analysis for this month
                month_setup = extract_period_setup_type_analysis(month_df, pnl_col)
                
                # Generate day-of-week analysis for this month
                month_day_of_week = extract_period_day_of_week_analysis(month_df, pnl_col)
                
                # Generate hourly analysis for this month
                month_hourly = extract_period_hourly_analysis(month_df, pnl_col)
                
                # Generate trading quarter analysis for this month
                month_trading_quarters = extract_period_trading_quarter_analysis(month_df, pnl_col)

                # Generate candle position analysis for this month
                month_candle_position = extract_hourly_candle_position_analysis(month_df, pnl_col)
                
                q_data[f"M{int(month):02d}"] = {
                    'summary': {
                        'trades': int(month_trades),
                        'wins': int(month_wins),
                        'losses': int(month_trades - month_wins),
                        'win_pct': round((month_wins / month_trades * 100) if month_trades > 0 else 0, 1),
                        'pnl': round(month_pnl, 2),
                        'avg_daily_total': month_avg_daily,
                        'avg_daily_longs': month_avg_daily_longs,
                        'avg_daily_shorts': month_avg_daily_shorts,
                    },
                    'weeks': month_data,
                    'by_day_of_week': month_day_of_week,
                    'by_hour': month_hourly,
                    'by_trading_quarter': month_trading_quarters,
                    'ladder_analysis': month_ladder,
                    'ladder_analysis_directional': month_ladder_directional,
                    'ladder_analysis_reversals': month_ladder_reversals,
                    'setup_type_by_entry_ladder': month_setup,
                    'candle_position_analysis': month_candle_position
                }
            
            # Quarter summary
            q_trades = len(q_df)
            q_wins = len(q_df[q_df['pnl_value'] > 0])
            q_pnl = q_df['pnl_value'].sum()
            q_days = len(q_df['day'].unique())
            q_avg_daily = round(q_trades / q_days, 1) if q_days > 0 else 0
            q_avg_daily_longs = round(len(q_df[q_df['direction'] == 'Long']) / q_days, 1) if q_days > 0 else 0
            q_avg_daily_shorts = round(len(q_df[q_df['direction'] == 'Short']) / q_days, 1) if q_days > 0 else 0
            
            # Generate ladder analysis for this quarter (all variants)
            q_ladder = extract_ladder_analysis(q_df, pnl_col)
            q_ladder_directional = extract_directional_ladder_analysis(q_df, pnl_col)
            q_ladder_reversals = extract_reversals_ladder_analysis(q_df, pnl_col)
            
            # Generate setup analysis for this quarter
            q_setup = extract_period_setup_type_analysis(q_df, pnl_col)
            
            # Generate day-of-week analysis for this quarter
            q_day_of_week = extract_period_day_of_week_analysis(q_df, pnl_col)
            
            # Generate hourly analysis for this quarter
            q_hourly = extract_period_hourly_analysis(q_df, pnl_col)
            
            # Generate trading quarter analysis for this quarter
            q_trading_quarters = extract_period_trading_quarter_analysis(q_df, pnl_col)

            # Generate candle position analysis for this quarter
            q_candle_position = extract_hourly_candle_position_analysis(q_df, pnl_col)
            
            year_data[f"Q{int(q)}"] = {
                'summary': {
                    'trades': int(q_trades),
                    'wins': int(q_wins),
                    'losses': int(q_trades - q_wins),
                    'win_pct': round((q_wins / q_trades * 100) if q_trades > 0 else 0, 1),
                    'pnl': round(q_pnl, 2),
                    'avg_daily_total': q_avg_daily,
                    'avg_daily_longs': q_avg_daily_longs,
                    'avg_daily_shorts': q_avg_daily_shorts,
                },
                'months': q_data,
                'by_day_of_week': q_day_of_week,
                'by_hour': q_hourly,
                'by_trading_quarter': q_trading_quarters,
                'ladder_analysis': q_ladder,
                'ladder_analysis_directional': q_ladder_directional,
                'ladder_analysis_reversals': q_ladder_reversals,
                'setup_type_by_entry_ladder': q_setup,
                'candle_position_analysis': q_candle_position
            }
        
        # Year summary
        year_trades = len(year_df)
        year_wins = len(year_df[year_df['pnl_value'] > 0])
        year_pnl = year_df['pnl_value'].sum()
        year_days = len(year_df['day'].unique())
        year_avg_daily = round(year_trades / year_days, 1) if year_days > 0 else 0
        year_avg_daily_longs = round(len(year_df[year_df['direction'] == 'Long']) / year_days, 1) if year_days > 0 else 0
        year_avg_daily_shorts = round(len(year_df[year_df['direction'] == 'Short']) / year_days, 1) if year_days > 0 else 0
        
        # Generate ladder analysis for this year (all variants)
        year_ladder = extract_ladder_analysis(year_df, pnl_col)
        year_ladder_directional = extract_directional_ladder_analysis(year_df, pnl_col)
        year_ladder_reversals = extract_reversals_ladder_analysis(year_df, pnl_col)
        
        # Generate setup analysis for this year
        year_setup = extract_period_setup_type_analysis(year_df, pnl_col)
        
        # Generate day-of-week analysis for this year
        year_day_of_week = extract_period_day_of_week_analysis(year_df, pnl_col)
        
        # Generate hourly analysis for this year
        year_hourly = extract_period_hourly_analysis(year_df, pnl_col)
        
        # Generate trading quarter analysis for this year
        year_trading_quarters = extract_period_trading_quarter_analysis(year_df, pnl_col)

        # Generate candle position analysis for this year
        year_candle_position = extract_hourly_candle_position_analysis(year_df, pnl_col)
        
        data_by_period[str(int(year))] = {
            'summary': {
                'trades': int(year_trades),
                'wins': int(year_wins),
                'losses': int(year_trades - year_wins),
                'win_pct': round((year_wins / year_trades * 100) if year_trades > 0 else 0, 1),
                'pnl': round(year_pnl, 2),
                'avg_daily_total': year_avg_daily,
                'avg_daily_longs': year_avg_daily_longs,
                'avg_daily_shorts': year_avg_daily_shorts,
            },
            'quarters': year_data,
            'by_day_of_week': year_day_of_week,
            'by_hour': year_hourly,
            'by_trading_quarter': year_trading_quarters,
            'ladder_analysis': year_ladder,
            'ladder_analysis_directional': year_ladder_directional,
            'ladder_analysis_reversals': year_ladder_reversals,
            'setup_type_by_entry_ladder': year_setup,
            'candle_position_analysis': year_candle_position
        }
    
    return data_by_period

def extract_hourly_candle_position_analysis(df, pnl_col):
    """
    Tests the hypothesis: are trades entered early in a new 1-hour candle
    more likely to fail (because the HTF candle hasn't built enough range yet,
    making a 65% bias reading potentially misleading)?

    Buckets each entry by how many minutes into the current hour candle it was
    placed (0-9, 10-19, 20-29, 30-39, 40-49, 50-59) and computes win rate,
    trade count, avg P&L, gross profit/loss. Also cross-references by hour of day.
    """
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}

    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])

    df['minute_into_hour'] = df['datetime'].dt.minute
    df['minute_bucket_start'] = (df['minute_into_hour'] // 10) * 10
    df['bucket_label'] = df['minute_bucket_start'].apply(lambda b: f"{b}-{b+9}")
    df['hour'] = df['datetime'].dt.hour
    df['hour_key'] = df['hour'].apply(lambda h: f"{h:02d}:00")

    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0)
    df['win'] = df['pnl_value'] > 0

    def bucket_stats(subset):
        n = len(subset)
        if n == 0:
            return None
        wins = int(subset['win'].sum())
        losses = n - wins
        pnl = float(subset['pnl_value'].sum())
        gp = float(subset.loc[subset['win'], 'pnl_value'].sum())
        gl = float(subset.loc[~subset['win'], 'pnl_value'].sum())
        aw = round(gp / wins, 2) if wins > 0 else 0
        al = round(gl / losses, 2) if losses > 0 else 0
        return {
            'trades': n,
            'wins': wins,
            'losses': losses,
            'win_pct': round(wins / n * 100, 1) if n > 0 else 0,
            'pnl': round(pnl, 2),
            'gross_profit': round(gp, 2),
            'gross_loss': round(gl, 2),
            'avg_win': aw,
            'avg_loss': al,
        }

    bucket_order = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59']

    by_bucket = {}
    for label in bucket_order:
        stats = bucket_stats(df[df['bucket_label'] == label])
        if stats:
            by_bucket[label] = stats

    # Cross-reference: by hour of day × minute bucket
    by_hour_and_bucket = {}
    for hk in sorted(df['hour_key'].unique()):
        hour_df = df[df['hour_key'] == hk]
        hour_buckets = {}
        for label in bucket_order:
            stats = bucket_stats(hour_df[hour_df['bucket_label'] == label])
            if stats:
                hour_buckets[label] = stats
        if hour_buckets:
            by_hour_and_bucket[hk] = hour_buckets

    return {
        'by_minute_bucket': by_bucket,
        'by_hour_and_bucket': by_hour_and_bucket,
        'bucket_order': bucket_order,
    }


def extract_hourly_analysis(df, pnl_col, trade_type='all'):
    """Extract trading analysis by hour of day (9:30-16:00).
    
    trade_type: 'all', 'directional', or 'reversals'
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Filter by trade type if specified
    if trade_type == 'directional':
        # Keep only primary direction trades (Bull Setup or Short Setup)
        df = df[df['Type'].str.contains('Bull Setup Entry|Short Setup Entry', na=False, case=False, regex=True)]
    elif trade_type == 'reversals':
        # Keep only reversal trades
        df = df[df['Type'].str.contains('Reversal', na=False, case=False)]
    # else 'all' - keep all entry trades
    
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Extract hour
    df['hour'] = df['datetime'].dt.hour
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Look for Points column (common variations)
    point_col = None
    for col in ['Points', 'points', 'Pts', 'pts', 'Point Value', 'point_value']:
        if col in df.columns:
            point_col = col
            break
    
    if point_col:
        df['point_value'] = pd.to_numeric(df[point_col], errors='coerce').fillna(0)
    else:
        df['point_value'] = 0
    
    # Aggregate by hour (9-16 for trading hours 9:30am-4:00pm)
    hourly_data = {}
    
    for hour in sorted(df['hour'].unique()):
        if hour < 9 or hour > 16:
            continue  # Skip pre/post market
        
        hour_df = df[df['hour'] == hour]
        hour_trades = len(hour_df)
        hour_wins = len(hour_df[hour_df['pnl_value'] > 0])
        hour_pnl = hour_df['pnl_value'].sum()
        
        # Gross profit/loss
        wins_df = hour_df[hour_df['pnl_value'] > 0]
        losses_df = hour_df[hour_df['pnl_value'] <= 0]
        gross_profit = wins_df['pnl_value'].sum() if not wins_df.empty else 0
        gross_loss = losses_df['pnl_value'].sum() if not losses_df.empty else 0
        
        # Points
        total_pts = hour_df['point_value'].sum() if point_col else 0
        avg_pts = (total_pts / hour_trades) if hour_trades > 0 else 0
        
        hourly_data[f"{hour:02d}:00"] = {
            'trades': int(hour_trades),
            'wins': int(hour_wins),
            'losses': int(hour_trades - hour_wins),
            'win_pct': round((hour_wins / hour_trades * 100) if hour_trades > 0 else 0, 1),
            'pnl': round(hour_pnl, 2),
            'wins_gross': round(gross_profit, 2),
            'losses_gross': round(gross_loss, 2),
            'point_value': round(total_pts, 1),
            'avg_pts': round(avg_pts, 1),
        }
    
    return hourly_data

def extract_day_of_week_analysis(df, pnl_col, trade_type='all'):
    """Extract trading analysis by day of week (Mon-Fri).
    
    trade_type: 'all', 'directional', or 'reversals'
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Filter by trade type if specified
    if trade_type == 'directional':
        # Keep only primary direction trades (Bull Setup or Short Setup)
        df = df[df['Type'].str.contains('Bull Setup Entry|Short Setup Entry', na=False, case=False, regex=True)]
    elif trade_type == 'reversals':
        # Keep only reversal trades
        df = df[df['Type'].str.contains('Reversal', na=False, case=False)]
    # else 'all' - keep all entry trades
    
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Extract day of week (0=Mon, 6=Sun)
    df['day_of_week'] = df['datetime'].dt.day_name()
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Aggregate by day
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    day_data = {}
    
    for day in days_order:
        day_df = df[df['day_of_week'] == day]
        if day_df.empty:
            continue
        
        day_trades = len(day_df)
        day_wins = len(day_df[day_df['pnl_value'] > 0])
        day_pnl = day_df['pnl_value'].sum()
        
        # Gross profit/loss
        wins_df = day_df[day_df['pnl_value'] > 0]
        losses_df = day_df[day_df['pnl_value'] <= 0]
        gross_profit = wins_df['pnl_value'].sum() if not wins_df.empty else 0
        gross_loss = losses_df['pnl_value'].sum() if not losses_df.empty else 0
        
        day_data[day] = {
            'trades': int(day_trades),
            'wins': int(day_wins),
            'losses': int(day_trades - day_wins),
            'win_pct': round((day_wins / day_trades * 100) if day_trades > 0 else 0, 1),
            'pnl': round(day_pnl, 2),
            'wins_gross': round(gross_profit, 2),
            'losses_gross': round(gross_loss, 2),
        }
    
    return day_data

def extract_trading_quarter_analysis(df, pnl_col, trade_type='all'):
    """Extract trading analysis by trading session quarter.
    
    Trading day: 9:30 AM - 4:00 PM (6.5 hours)
    Q1: 9:30-11:30 (Opening)
    Q2: 11:30-13:00 (Lunch Approach)  
    Q3: 13:00-15:00 (Post-Lunch)
    Q4: 15:00-16:00 (Close)
    
    trade_type: 'all', 'directional', or 'reversals'
    """
    if df.empty or 'Date and time' not in df.columns:
        return {}
    
    # Filter for entry trades only
    df = df[df['Type'].str.contains('Entry', na=False, case=False)].copy()
    if df.empty:
        return {}
    
    # Filter by trade type if specified
    if trade_type == 'directional':
        # Keep only primary direction trades (Bull Setup or Short Setup)
        df = df[df['Type'].str.contains('Bull Setup Entry|Short Setup Entry', na=False, case=False, regex=True)]
    elif trade_type == 'reversals':
        # Keep only reversal trades
        df = df[df['Type'].str.contains('Reversal', na=False, case=False)]
    # else 'all' - keep all entry trades
    
    if df.empty:
        return {}
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['Date and time'], errors='coerce')
    df = df.dropna(subset=['datetime'])
    
    # Convert PnL to numeric
    df['pnl_value'] = pd.to_numeric(df[pnl_col], errors='coerce')
    
    # Look for Points column (common variations)
    point_col = None
    for col in ['Points', 'points', 'Pts', 'pts', 'Point Value', 'point_value']:
        if col in df.columns:
            point_col = col
            break
    
    if point_col:
        df['point_value'] = pd.to_numeric(df[point_col], errors='coerce').fillna(0)
    else:
        df['point_value'] = 0
    
    # Assign trading quarter based on time
    def get_trading_quarter(dt):
        hour = dt.hour
        minute = dt.minute
        total_minutes = hour * 60 + minute
        
        # 9:30am = 570 minutes, 4:00pm = 1040 minutes
        market_open = 9 * 60 + 30  # 570
        
        if total_minutes < market_open:
            return None  # Pre-market
        elif total_minutes >= market_open and total_minutes < (11 * 60 + 30):  # 9:30-11:30
            return 'Q1 (09:30-11:30) Opening'
        elif total_minutes >= (11 * 60 + 30) and total_minutes < (13 * 60):  # 11:30-13:00
            return 'Q2 (11:30-13:00) Lunch Approach'
        elif total_minutes >= (13 * 60) and total_minutes < (15 * 60):  # 13:00-15:00
            return 'Q3 (13:00-15:00) Post-Lunch'
        elif total_minutes >= (15 * 60) and total_minutes < 16 * 60 + 60:  # 15:00-16:00+
            return 'Q4 (15:00-16:00) Close'
        else:
            return None  # Post-market
    
    df['trading_quarter'] = df['datetime'].apply(get_trading_quarter)
    df = df.dropna(subset=['trading_quarter'])
    
    # Aggregate by quarter
    quarter_data = {}
    quarters_order = [
        'Q1 (09:30-11:30) Opening',
        'Q2 (11:30-13:00) Lunch Approach',
        'Q3 (13:00-15:00) Post-Lunch',
        'Q4 (15:00-16:00) Close'
    ]
    
    for quarter in quarters_order:
        quarter_df = df[df['trading_quarter'] == quarter]
        if quarter_df.empty:
            continue
        
        q_trades = len(quarter_df)
        q_wins = len(quarter_df[quarter_df['pnl_value'] > 0])
        q_pnl = quarter_df['pnl_value'].sum()
        q_avg = quarter_df['pnl_value'].mean()
        
        # Gross profit/loss
        wins_df = quarter_df[quarter_df['pnl_value'] > 0]
        losses_df = quarter_df[quarter_df['pnl_value'] <= 0]
        gross_profit = wins_df['pnl_value'].sum() if not wins_df.empty else 0
        gross_loss = losses_df['pnl_value'].sum() if not losses_df.empty else 0
        
        # Points
        total_pts = quarter_df['point_value'].sum() if point_col else 0
        avg_pts = (total_pts / q_trades) if q_trades > 0 else 0
        
        quarter_data[quarter] = {
            'trades': int(q_trades),
            'wins': int(q_wins),
            'losses': int(q_trades - q_wins),
            'win_pct': round((q_wins / q_trades * 100) if q_trades > 0 else 0, 1),
            'pnl': round(q_pnl, 2),
            'avg_pnl': round(q_avg, 2),
            'wins_gross': round(gross_profit, 2),
            'losses_gross': round(gross_loss, 2),
            'point_value': round(total_pts, 1),
            'avg_pts': round(avg_pts, 1),
        }
    
    return quarter_data

def main():
    print("🔄 Updating dashboard data...")
    
    # Find latest files — NQ contains MNQ, ES contains MES
    def find_instrument_file(directory, patterns):
        """Find most recent file matching any of the given name patterns."""
        files = list(directory.glob("**/*.csv")) + list(directory.glob("**/*.xlsx"))
        matched = [f for f in files if any(p.lower() in f.name.lower() for p in patterns)]
        if not matched:
            return None
        return max(matched, key=lambda p: (p.stat().st_size, p.stat().st_mtime))

    nq_file = find_instrument_file(DATA_DIR, ['MNQ', 'NQ'])
    es_file = find_instrument_file(DATA_DIR, ['MES', 'ES'])
    
    if not nq_file or not es_file:
        print("❌ Could not find NQ or ES files")
        return
    
    print(f"📊 NQ/MNQ: {nq_file.name}")
    print(f"📊 ES/MES: {es_file.name}")
    
    # Load data
    try:
        nq_df = load_data(nq_file)
        es_df = load_data(es_file)
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return
    
    # Find date and P&L columns
    date_col_nq = next((c for c in ['Date and time', 'Date', 'date', 'Entry Date', 'open_time'] if c in nq_df.columns), nq_df.columns[0])
    pnl_col_nq = next((c for c in ['Net P&L USD', 'P&L', 'pnl', 'profit', 'Profit', 'net_profit'] if c in nq_df.columns), None)
    
    date_col_es = next((c for c in ['Date and time', 'Date', 'date', 'Entry Date', 'open_time'] if c in es_df.columns), es_df.columns[0])
    pnl_col_es = next((c for c in ['Net P&L USD', 'P&L', 'pnl', 'profit', 'Profit', 'net_profit'] if c in es_df.columns), None)
    
    if not pnl_col_nq or not pnl_col_es:
        print("❌ Could not find P&L columns in data")
        return
    
    # Aggregate data
    print("📈 Aggregating NQ data...")
    nq_data = aggregate_by_period(nq_df, date_col_nq, pnl_col_nq)
    
    print("📈 Extracting NQ ladder analysis (all trades)...")
    nq_ladder_all = extract_ladder_analysis(nq_df, pnl_col_nq)
    
    print("📈 Extracting NQ ladder analysis (directional only)...")
    nq_ladder_directional = extract_directional_ladder_analysis(nq_df, pnl_col_nq)
    
    print("📈 Extracting NQ ladder analysis (reversals only)...")
    nq_ladder_reversals = extract_reversals_ladder_analysis(nq_df, pnl_col_nq)
    
    print("📈 Extracting NQ setup type analysis...")
    nq_setup = extract_setup_type_analysis(nq_df, pnl_col_nq)

    print("📈 Extracting NQ risk & reward summary...")
    nq_risk_reward = extract_risk_reward_summary(nq_df, pnl_col_nq)

    print("📈 Extracting NQ trade analysis (streaks, drawdown, duration)...")
    nq_trade_analysis = extract_trade_analysis(nq_df, pnl_col_nq)

    print("📈 Extracting NQ hourly candle position analysis (minutes-into-hour hypothesis)...")
    nq_candle_position = extract_hourly_candle_position_analysis(nq_df, pnl_col_nq)

    print("📈 Aggregating ES data...")
    es_data = aggregate_by_period(es_df, date_col_es, pnl_col_es)
    
    print("📈 Extracting ES ladder analysis (all trades)...")
    es_ladder_all = extract_ladder_analysis(es_df, pnl_col_es)
    
    print("📈 Extracting ES ladder analysis (directional only)...")
    es_ladder_directional = extract_directional_ladder_analysis(es_df, pnl_col_es)
    
    print("📈 Extracting ES ladder analysis (reversals only)...")
    es_ladder_reversals = extract_reversals_ladder_analysis(es_df, pnl_col_es)
    
    print("📈 Extracting ES setup type analysis...")
    es_setup = extract_setup_type_analysis(es_df, pnl_col_es)

    print("📈 Extracting ES risk & reward summary...")
    es_risk_reward = extract_risk_reward_summary(es_df, pnl_col_es)

    print("📈 Extracting ES trade analysis (streaks, drawdown, duration)...")
    es_trade_analysis = extract_trade_analysis(es_df, pnl_col_es)

    print("📈 Extracting ES hourly candle position analysis (minutes-into-hour hypothesis)...")
    es_candle_position = extract_hourly_candle_position_analysis(es_df, pnl_col_es)

    print("📈 Extracting NQ setup type by entry ladder with P&L...")
    nq_setup_pnl = extract_setup_type_by_entry_ladder_with_pnl(nq_df, pnl_col_nq)
    
    print("📈 Extracting ES setup type by entry ladder with P&L...")
    es_setup_pnl = extract_setup_type_by_entry_ladder_with_pnl(es_df, pnl_col_es)
    
    print("📈 Calculating NQ trade breakdown (primary vs reversals)...")
    nq_breakdown = calculate_trade_breakdown(nq_df)
    
    print("📈 Calculating ES trade breakdown (primary vs reversals)...")
    es_breakdown = calculate_trade_breakdown(es_df)
    
    print("📈 Extracting NQ temporal analysis (hourly)...")
    nq_hourly = extract_hourly_analysis(nq_df, pnl_col_nq, 'all')
    nq_hourly_directional = extract_hourly_analysis(nq_df, pnl_col_nq, 'directional')
    nq_hourly_reversals = extract_hourly_analysis(nq_df, pnl_col_nq, 'reversals')
    
    print("📈 Extracting NQ temporal analysis (day of week)...")
    nq_day_of_week = extract_day_of_week_analysis(nq_df, pnl_col_nq, 'all')
    nq_day_of_week_directional = extract_day_of_week_analysis(nq_df, pnl_col_nq, 'directional')
    nq_day_of_week_reversals = extract_day_of_week_analysis(nq_df, pnl_col_nq, 'reversals')
    
    print("📈 Extracting NQ temporal analysis (trading quarters)...")
    nq_trading_quarters = extract_trading_quarter_analysis(nq_df, pnl_col_nq, 'all')
    nq_trading_quarters_directional = extract_trading_quarter_analysis(nq_df, pnl_col_nq, 'directional')
    nq_trading_quarters_reversals = extract_trading_quarter_analysis(nq_df, pnl_col_nq, 'reversals')
    
    print("📈 Extracting ES temporal analysis (hourly)...")
    es_hourly = extract_hourly_analysis(es_df, pnl_col_es, 'all')
    es_hourly_directional = extract_hourly_analysis(es_df, pnl_col_es, 'directional')
    es_hourly_reversals = extract_hourly_analysis(es_df, pnl_col_es, 'reversals')
    
    print("📈 Extracting ES temporal analysis (day of week)...")
    es_day_of_week = extract_day_of_week_analysis(es_df, pnl_col_es, 'all')
    es_day_of_week_directional = extract_day_of_week_analysis(es_df, pnl_col_es, 'directional')
    es_day_of_week_reversals = extract_day_of_week_analysis(es_df, pnl_col_es, 'reversals')
    
    print("📈 Extracting ES temporal analysis (trading quarters)...")
    es_trading_quarters = extract_trading_quarter_analysis(es_df, pnl_col_es, 'all')
    es_trading_quarters_directional = extract_trading_quarter_analysis(es_df, pnl_col_es, 'directional')
    es_trading_quarters_reversals = extract_trading_quarter_analysis(es_df, pnl_col_es, 'reversals')
    
    # Build output
    output = {
        'updated': datetime.now().isoformat(),
        'instruments': {
            'NQ/MNQ': {
                'by_period': nq_data,
                'ladder_analysis': nq_ladder_all,
                'ladder_analysis_directional': nq_ladder_directional,
                'ladder_analysis_reversals': nq_ladder_reversals,
                'setup_type_analysis': nq_setup,
                'setup_type_by_entry_ladder': nq_setup_pnl,
                'trade_breakdown': nq_breakdown,
                'by_hour': nq_hourly,
                'by_hour_directional': nq_hourly_directional,
                'by_hour_reversals': nq_hourly_reversals,
                'by_day_of_week': nq_day_of_week,
                'by_day_of_week_directional': nq_day_of_week_directional,
                'by_day_of_week_reversals': nq_day_of_week_reversals,
                'by_trading_quarter': nq_trading_quarters,
                'by_trading_quarter_directional': nq_trading_quarters_directional,
                'by_trading_quarter_reversals': nq_trading_quarters_reversals,
                'risk_reward': nq_risk_reward,
                'trade_analysis': nq_trade_analysis,
                'candle_position_analysis': nq_candle_position
            },
            'ES/MES': {
                'by_period': es_data,
                'ladder_analysis': es_ladder_all,
                'ladder_analysis_directional': es_ladder_directional,
                'ladder_analysis_reversals': es_ladder_reversals,
                'setup_type_analysis': es_setup,
                'setup_type_by_entry_ladder': es_setup_pnl,
                'trade_breakdown': es_breakdown,
                'by_hour': es_hourly,
                'by_hour_directional': es_hourly_directional,
                'by_hour_reversals': es_hourly_reversals,
                'by_day_of_week': es_day_of_week,
                'by_day_of_week_directional': es_day_of_week_directional,
                'by_day_of_week_reversals': es_day_of_week_reversals,
                'by_trading_quarter': es_trading_quarters,
                'by_trading_quarter_directional': es_trading_quarters_directional,
                'by_trading_quarter_reversals': es_trading_quarters_reversals,
                'risk_reward': es_risk_reward,
                'trade_analysis': es_trade_analysis,
                'candle_position_analysis': es_candle_position
            }
        }
    }
    
    # Print breakdown summary
    print("\n📊 Trade Breakdown Summary:")
    print(f"NQ/MNQ: Total={nq_breakdown.get('total_trades', 0)} | Primary={nq_breakdown.get('primary_direction', {}).get('total', 0)} | Reversals={nq_breakdown.get('reversals', {}).get('total', 0)}")
    print(f"ES/MES: Total={es_breakdown.get('total_trades', 0)} | Primary={es_breakdown.get('primary_direction', {}).get('total', 0)} | Reversals={es_breakdown.get('reversals', {}).get('total', 0)}")
    
    # Save JSON to data/ and reports/ (reports/ needed for local dashboard fetch)
    json_str = json.dumps(output, indent=2)
    with open(OUTPUT_FILE, 'w') as f:
        f.write(json_str)
    REPORTS_FILE = BASE_PATH.parent / "reports" / "dashboard_data.json"
    with open(REPORTS_FILE, 'w') as f:
        f.write(json_str)
    
    print(f"✅ Dashboard data saved to {OUTPUT_FILE.name}")
    print(f"   Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
