import pandas as pd

file_path = r"C:\仓库\Antigravity-Manager\pagogo1.0\金蝶凭证导入模板.xls"

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

try:
    # Check Page1 specifically
    print("\nReading Page1 sheet (potential user-facing template)...")
    df_p1 = pd.read_excel(file_path, sheet_name='Page1', header=None, nrows=10)
    print("First 10 rows of Page1:")
    for index, row in df_p1.iterrows():
        print(f"Row {index}: {row.tolist()}")

except Exception as e:
    print(f"Error: {e}")
