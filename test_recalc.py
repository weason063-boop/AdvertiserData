import sys
import pandas as pd
import os

sys.path.append('C:/仓库/Antigravity-Manager/账单')
from api.services.calculation_service import CalculationService

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

svc = CalculationService()
print("Starting recalculate...")
try:
    res = svc.recalculate_latest(owner_username="test_script")
    print("Recalculate complete:", res['output_file'])
    
    output_path = os.path.join('C:/仓库/Antigravity-Manager/账单/uploads', res['output_file'])
    df = pd.read_excel(output_path)
    acmer_rows = df[df['母公司'].str.contains('acmer', case=False, na=False)]
    if not acmer_rows.empty:
        display_cols = [c for c in ['母公司', '媒介', '服务类型', '代投消耗', '服务费', '固定服务费'] if c in df.columns]
        print("\n--- ACMER ROWS IN NEW RESULT ---")
        print(acmer_rows[display_cols].to_string())
    else:
        print("\nNo Acmer rows found.")
except Exception as e:
    print("Error during recalculation:", e)
