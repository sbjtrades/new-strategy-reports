import pandas as pd
import re
from collections import defaultdict

# Load NQ data
nq_file = "./nq-mnq/master-report-nq/30-sec-or-rotations-UL.DL10.3bar.Core_CME_MINI_MNQ1!_2023-06-15-2026-04-14_8f9af.xlsx"
nq_df = pd.read_excel(nq_file, sheet_name='List of trades')

# Filter for entry trades only
entries = nq_df[nq_df['Type'].str.contains('Entry', na=False)].copy()

print("=== LADDER & SETUP TYPE PARSING ===\n")

# Parse Signal column
def parse_signal(signal):
    """Extract setup type and ladder transition from signal string"""
    if pd.isna(signal):
        return None, None, None
    
    signal = str(signal)
    
    # Extract setup type (BS, SS, RS, RL, etc.) - usually 2 letters at start
    setup_match = re.match(r'^([A-Z]{2})\s+', signal)
    setup_type = setup_match.group(1) if setup_match else None
    
    # Extract ladder transition (e.g., UL1→UL2, DL1→ORL, etc.)
    ladder_match = re.search(r'(UL\d+|DL\d+|ORL|ORH)→(UL\d+|DL\d+|ORL|ORH)', signal)
    
    if ladder_match:
        from_ladder = ladder_match.group(1)
        to_ladder = ladder_match.group(2)
        return setup_type, from_ladder, to_ladder
    
    return setup_type, None, None

# Apply parsing
entries['setup_type'] = entries['Signal'].apply(lambda x: parse_signal(x)[0])
entries['from_ladder'] = entries['Signal'].apply(lambda x: parse_signal(x)[1])
entries['to_ladder'] = entries['Signal'].apply(lambda x: parse_signal(x)[2])

print("Setup Types Found:")
print(entries['setup_type'].value_counts())
print()

print("Ladder Transitions Found (Top 15):")
transitions = entries.groupby(['from_ladder', 'to_ladder']).size().sort_values(ascending=False)
for (from_l, to_l), count in transitions.head(15).items():
    print(f"  {from_l} → {to_l}: {count}")

print()
print("All Unique Ladder Types:")
all_ladders = set()
all_ladders.update(entries['from_ladder'].dropna().unique())
all_ladders.update(entries['to_ladder'].dropna().unique())
print(f"  {sorted([l for l in all_ladders if pd.notna(l)])}")

print()
print("Setup Type + Ladder Direction Combinations (Top 10):")
combo_counts = entries.groupby(['setup_type', 'from_ladder', 'to_ladder']).size().sort_values(ascending=False)
for (setup, from_l, to_l), count in combo_counts.head(10).items():
    print(f"  {setup} {from_l}→{to_l}: {count}")

