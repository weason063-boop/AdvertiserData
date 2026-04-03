import sqlite3
import pandas as pd
import re

conn = sqlite3.connect('C:/仓库/Antigravity-Manager/账单/contracts.db')
df = pd.read_sql_query('SELECT DISTINCT fee_clause FROM client_contract_lines', conn)
clauses = df['fee_clause'].dropna().unique().tolist()

# 筛选可能包含固定服务费的条款
fixed_fee_clauses = [
    c for c in clauses 
    if re.search(r'固定|各\s*\d+|[+＋]\s*\d+(?!\s*%)|\d+\s*/\s*月|保底|[-~−–]\s*\d+[wW万]?\s*[，,]?\s*(?:服务费)?\s*\d+(?!\s*%)', str(c))
]

print('=== FIXED FEE CLAUSES ===')
for c in fixed_fee_clauses:
    print("-", str(c).replace('\n', ' '))
