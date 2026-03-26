import pandas as pd
import sys

file_path = r"C:\仓库\Antigravity-Manager\pagogo1.0\金蝶凭证导入模板.xls"

try:
    xl = pd.ExcelFile(file_path)
    print(f"Sheet names: {xl.sheet_names}")
    
    for sheet_name in xl.sheet_names:
        print(f"\nScanning Sheet: {sheet_name}")
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=20)
        print(df.to_string())

except Exception as e:
    print(f"Error reading Excel file: {e}")
