import pandas as pd
import sys
from pathlib import Path

# Adjust path if needed
file_path = r"c:\仓库\Antigravity-Manager\账单\uploads\2025年美金汇总-谷歌渠道消耗明细_计算结果.xlsx"

print(f"Reading: {file_path}")
try:
    df = pd.read_excel(file_path)
    print(f"Columns: {df.columns.tolist()}")
    
    # Check for fuzzy match
    for col in df.columns:
        if '月份' in str(col) or 'Month' in str(col):
            print(f"Match found: '{col}'")
            print(df[col].head())
            first_val = df[col].iloc[0]
            print(f"First value: {first_val} (Type: {type(first_val)})")
            
            try:
                dt = pd.to_datetime(first_val)
                print(f"Parsed datetime: {dt} -> {dt.strftime('%Y-%m')}")
            except Exception as e:
                print(f"Parsing error: {e}")

except Exception as e:
    print(f"Error reading file: {e}")
