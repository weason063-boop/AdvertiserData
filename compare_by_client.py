import pandas as pd
import numpy as np

print("=" * 80)
print("Client-Level Discrepancy Analysis")
print("=" * 80)

# Files
auto_file = '2026年1月消耗明细_results.xlsx'
manual_file = '手工计算.xlsx'

try:
    df_auto = pd.read_excel(auto_file)
    df_manual = pd.read_excel(manual_file)
except FileNotFoundError as e:
    print(f"Error: {e}")
    exit(1)

# Normalize column names (strip whitespace/newlines)
df_auto.columns = df_auto.columns.str.strip()
df_manual.columns = df_manual.columns.str.strip()

# Normalize client names
if '母公司' in df_auto.columns:
    df_auto['母公司'] = df_auto['母公司'].astype(str).str.strip()
if '母公司' in df_manual.columns:
    df_manual['母公司'] = df_manual['母公司'].astype(str).str.strip()

# Ensure numeric columns
for col in ['服务费', '固定服务费', '代投消耗', '流水消耗']:
    if col in df_manual.columns:
        df_manual[col] = pd.to_numeric(df_manual[col], errors='coerce').fillna(0.0)
    else:
        df_manual[col] = 0.0
    
    if col in df_auto.columns:
        df_auto[col] = pd.to_numeric(df_auto[col], errors='coerce').fillna(0.0)

# Group by Client
def aggregate_client(df, suffix):
    # Fill NaN with 0
    df = df.fillna(0)
    # Ensure consumption columns exist
    if '代投消耗' not in df.columns: df['代投消耗'] = 0
    if '流水消耗' not in df.columns: df['流水消耗'] = 0
    
    # Group by '母公司' and sum fees and consumption
    grp = df.groupby('母公司')[['服务费', '固定服务费', '代投消耗', '流水消耗']].sum()
    grp.columns = [f'{c}_{suffix}' for c in grp.columns]
    return grp

grp_auto = aggregate_client(df_auto, 'Auto')
grp_manual = aggregate_client(df_manual, 'Manual')

# Merge
comparison = pd.concat([grp_auto, grp_manual], axis=1).fillna(0)

# Calculate Differences
comparison['Service_Diff'] = comparison['服务费_Auto'] - comparison['服务费_Manual']
comparison['Fixed_Diff'] = comparison['固定服务费_Auto'] - comparison['固定服务费_Manual']
comparison['Total_Diff'] = comparison['Service_Diff'] + comparison['Fixed_Diff']

# Filter for discrepancies (tolerance $1.00)
tolerance = 1.0
discrepancies = comparison[abs(comparison['Total_Diff']) > tolerance].copy()

# Sort by absolute total difference
discrepancies['Abs_Diff'] = abs(discrepancies['Total_Diff'])
discrepancies = discrepancies.sort_values('Abs_Diff', ascending=False)

# Write to file
with open('discrepancy_report.txt', 'w', encoding='utf-8') as f:
    f.write(f"Found {len(discrepancies)} clients with discrepancies > ${tolerance}:\n\n")

    for client, row in discrepancies.iterrows():
        f.write(f"🔴 Client: {client}\n")
        f.write(f"   Total Diff: ${row['Total_Diff']:,.2f}\n")
        f.write(f"   Consumption: Auto(Daitou=${row['代投消耗_Auto']:,.2f}, Liushui=${row['流水消耗_Auto']:,.2f})\n")
        
        # Detailed breakdown
        if abs(row['Service_Diff']) > 0.1:
            f.write(f"     Service Fee: Auto ${row['服务费_Auto']:,.2f} vs Manual ${row['服务费_Manual']:,.2f} (Diff: ${row['Service_Diff']:,.2f})\n")
        if abs(row['Fixed_Diff']) > 0.1:
            f.write(f"     Fixed Fee  : Auto ${row['固定服务费_Auto']:,.2f} vs Manual ${row['固定服务费_Manual']:,.2f} (Diff: ${row['Fixed_Diff']:,.2f})\n")
        f.write("-" * 40 + "\n")

    # Specific check for '能用'
    f.write("\n🔍 Checking '能用' (Nengyong) specifically:\n")
    nengyong = comparison[comparison.index.str.contains('能用', na=False)]
    if not nengyong.empty:
        f.write(nengyong.to_string())
    else:
        f.write("Client '能用' not found in aggregated data.\n")

print("Report saved to discrepancy_report.txt")
