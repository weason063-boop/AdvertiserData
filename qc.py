import sqlite3
import pandas as pd
import glob
import os

conn = sqlite3.connect('C:/仓库/Antigravity-Manager/账单/contracts.db')
df_clause = pd.read_sql_query("SELECT DISTINCT client_name, fee_clause FROM client_contract_lines WHERE client_name LIKE '%通威%'", conn)
print("=== 通威股份 合同条款 ===")
print(df_clause.to_string())

print("\n=== 通威股份 最新计算行 ===")
files = glob.glob('C:/仓库/Antigravity-Manager/账单/uploads/*_results.xlsx')
if files:
    latest = max(files, key=os.path.getctime)
    df = pd.read_excel(latest)
    mask = df['母公司'].astype(str).str.contains('通威', na=False)
    rows = df[mask]
    cols = [c for c in ['母公司','媒介','服务类型','代投消耗','流水消耗','服务费','固定服务费'] if c in df.columns]
    print(rows[cols].to_string())
    
    # 显示原始精确值（不格式化）
    print("\n=== 精确消耗值（16位精度）===")
    for _, row in rows.iterrows():
        consumption = row.get('代投消耗', 0) or row.get('流水消耗', 0)
        print(f"  媒介={row.get('媒介')}, 消耗(raw)={repr(consumption)}")
