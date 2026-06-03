#!/usr/bin/env python3
"""
update.py — Weekly forward test updater for 30-Sec OR Strategy Hub

Usage:
    python3 update.py --week "Jun 3-6" --notes "First week live"

What it does:
1. Loads new alert CSV(s) from ALERT_DROPS_DIR
2. Loads new OHLC CSV(s) from OHLC_DROPS_DIR
3. Runs forward-walk to determine TP/SL outcomes
4. Applies 30-min ≥60% confluence filter
5. Appends a week entry to forward_test.json
6. Updates last_updated timestamp

Drop files here before running:
  Alerts: 05 - journal/trades/trading-view-alerts/   (TradingView alert CSV)
  OHLC:   04 - reporting-dashboards/probability-dashboard/v1/data/raw/accumulator/

The script processes ALL alerts in the trading-view-alerts folder that fall
within the date range of the OHLC data available. It deduplicates against
weeks already recorded in forward_test.json by UTC timestamp.
"""

import argparse, bisect, csv, json, os, sys
from datetime import datetime, timedelta, timezone

# ── Config ────────────────────────────────────────────────────────────────────
VAULT  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# If running from the hub folder itself:
if not os.path.exists(os.path.join(VAULT, '05 - journal')):
    VAULT = os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SJ Work Vault"
    )

HUB        = os.path.dirname(os.path.abspath(__file__))
OHLC_DIRS  = [
    os.path.join(VAULT, "04 - reporting-dashboards/probability-dashboard/v1/data/raw/archive/legacy"),
    os.path.join(VAULT, "04 - reporting-dashboards/probability-dashboard/v1/data/raw/accumulator"),
]
ALERT_DIR  = os.path.join(VAULT, "05 - journal/trades/trading-view-alerts")
FT_JSON    = os.path.join(HUB, "forward_test.json")
HTF_JSON   = os.path.join(HUB, "htf_research.json")
MNQ_MULT   = 2.0
CONF_TF    = 30        # 30-minute HTF
CONF_THRESH = 0.60     # ≥60% body/range


def load_ohlc():
    bars = {}
    for d in OHLC_DIRS:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith('.csv'):
                continue
            with open(os.path.join(d, fname)) as f:
                for row in csv.DictReader(f):
                    try:
                        dt = datetime.fromisoformat(row['time']).astimezone(timezone.utc).replace(tzinfo=None)
                        bars[dt] = {
                            'o': float(row['open']), 'h': float(row['high']),
                            'l': float(row['low']),  'c': float(row['close'])
                        }
                    except Exception:
                        pass
    return bars


def build_htf(bars, bar_times, tf_min):
    htf = {}
    for bt in bar_times:
        az    = bt - timedelta(hours=7)
        total = az.hour * 60 + az.minute
        slot  = total // tf_min * tf_min
        slot_az = az.replace(hour=slot // 60, minute=slot % 60, second=0, microsecond=0)
        k = slot_az + timedelta(hours=7)
        b = bars[bt]
        if k not in htf:
            htf[k] = {'o': b['o'], 'h': b['h'], 'l': b['l'], 'c': b['c']}
        else:
            htf[k]['h'] = max(htf[k]['h'], b['h'])
            htf[k]['l'] = min(htf[k]['l'], b['l'])
            htf[k]['c'] = b['c']
    return htf


def get_conf(dt_utc, direction, htf, tf_min):
    az    = dt_utc - timedelta(hours=7)
    total = az.hour * 60 + az.minute
    slot  = total // tf_min * tf_min
    slot_az = az.replace(hour=slot // 60, minute=slot % 60, second=0, microsecond=0)
    k = slot_az + timedelta(hours=7)
    if k not in htf:
        return None
    c   = htf[k]
    rng = c['h'] - c['l']
    if rng < 1:
        return None
    body = c['c'] - c['o']
    return (body / rng) if direction == 'buy' else (-body / rng)


def resolve(a, bars, bar_times):
    utc = datetime.fromisoformat(a['utc'])
    lng = a['dir'] == 'buy'
    tp, sl = a['tp'], a['sl']
    idx = bisect.bisect_left(bar_times, utc)
    for bt in bar_times[idx: idx + 400]:
        b = bars[bt]
        th = b['h'] >= tp if lng else b['l'] <= tp
        sh = b['l'] <= sl if lng else b['h'] >= sl
        if th and sh:
            return 'ambiguous'
        if th:
            return 'win'
        if sh:
            return 'loss'
    return 'timeout'


def load_alerts(bar_times):
    alerts = []
    for fname in os.listdir(ALERT_DIR):
        if not fname.endswith('.csv'):
            continue
        with open(os.path.join(ALERT_DIR, fname)) as f:
            for row in csv.DictReader(f):
                try:
                    utc = datetime.fromisoformat(row['Time'].replace('Z', '+00:00')).replace(tzinfo=None)
                    az  = utc - timedelta(hours=7)
                    tm  = az.hour * 60 + az.minute
                    if tm < 6 * 60 + 30 or tm >= 15 * 60:
                        continue
                    if not (bar_times[0] <= utc <= bar_times[-1]):
                        continue
                    d  = json.loads(row['Description'])
                    e  = float(d.get('signalPrice', 0))
                    tp = float(d.get('takeProfit', {}).get('limitPrice', 0))
                    sl = float(d.get('stopLoss', {}).get('stopPrice', 0))
                    if not e or not tp or not sl:
                        continue
                    alerts.append({
                        'utc': utc.isoformat(),
                        'dir': d.get('action', ''),
                        'e': e, 'tp': tp, 'sl': sl,
                        'tp_pts': abs(tp - e),
                        'sl_pts': abs(sl - e),
                    })
                except Exception:
                    pass
    return alerts


def compute_week_stats(alerts, bars, bar_times, htf_30):
    """Resolve outcomes + apply 30-min ≥60% confluence filter. Return stats dict."""
    resolved = []
    for a in alerts:
        out = resolve(a, bars, bar_times)
        if out not in ('win', 'loss'):
            continue
        utc  = datetime.fromisoformat(a['utc'])
        c30  = get_conf(utc, a['dir'], htf_30, CONF_TF)
        if c30 is None or c30 < CONF_THRESH:
            continue
        pnl  = a['tp_pts'] * MNQ_MULT if out == 'win' else -a['sl_pts'] * MNQ_MULT
        resolved.append({'out': out, 'pnl': round(pnl, 2)})

    wins   = sum(1 for r in resolved if r['out'] == 'win')
    losses = len(resolved) - wins
    pnl    = round(sum(r['pnl'] for r in resolved), 2)
    wr     = round(wins / len(resolved) * 100, 1) if resolved else 0.0
    return {'signals': len(resolved), 'wins': wins, 'losses': losses, 'wr': wr, 'pnl': pnl}


def get_already_seen_utcs(ft_data):
    """Return set of UTC timestamps already recorded (to avoid duplicates)."""
    seen = set()
    for week in ft_data.get('weeks', []):
        for ts in week.get('alert_utcs', []):
            seen.add(ts)
    return seen


def main():
    parser = argparse.ArgumentParser(description='Update forward_test.json with a new week.')
    parser.add_argument('--week', required=True, help='Week label, e.g. "Jun 3-6"')
    parser.add_argument('--notes', default='', help='Optional notes for this week')
    parser.add_argument('--dry-run', action='store_true', help='Print results without saving')
    args = parser.parse_args()

    print('Loading OHLC bars…')
    bars = load_ohlc()
    if not bars:
        print('ERROR: No OHLC bars found. Check OHLC_DIRS paths.')
        sys.exit(1)
    bar_times = sorted(bars.keys())
    print(f'  {len(bar_times):,} bars loaded ({bar_times[0]} → {bar_times[-1]})')

    htf_30 = build_htf(bars, bar_times, CONF_TF)
    print(f'  {len(htf_30):,} 30-min HTF bars built')

    # Load existing forward_test.json
    with open(FT_JSON) as f:
        ft_data = json.load(f)
    already_seen = get_already_seen_utcs(ft_data)

    print('Loading alerts…')
    all_alerts = load_alerts(bar_times)
    # Exclude already-processed alerts
    new_alerts = [a for a in all_alerts if a['utc'] not in already_seen]
    print(f'  {len(all_alerts)} total alerts in window, {len(new_alerts)} new (unseen)')

    if not new_alerts:
        print('No new alerts to process. Is the alert CSV for this week loaded?')
        sys.exit(0)

    print('Computing outcomes…')
    stats = compute_week_stats(new_alerts, bars, bar_times, htf_30)
    print(f'\n  Week: {args.week}')
    print(f'  Signals (after filter): {stats["signals"]}')
    print(f'  Wins: {stats["wins"]}  Losses: {stats["losses"]}')
    print(f'  Win Rate: {stats["wr"]:.1f}%')
    print(f'  PnL: ${stats["pnl"]:,.2f}')

    if args.dry_run:
        print('\nDry run — forward_test.json NOT updated.')
        return

    week_entry = {
        'week': args.week,
        'signals': stats['signals'],
        'wins': stats['wins'],
        'losses': stats['losses'],
        'wr': stats['wr'],
        'pnl': stats['pnl'],
        'notes': args.notes,
        'alert_utcs': [a['utc'] for a in new_alerts],  # for deduplication
        'added': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
    }
    ft_data['weeks'].append(week_entry)
    ft_data['last_updated'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    with open(FT_JSON, 'w') as f:
        json.dump(ft_data, f, indent=2)
    print(f'\nSaved → {FT_JSON}')
    print('Next step: git add -A && git commit -m "week: ' + args.week + '" && git push')


if __name__ == '__main__':
    main()
