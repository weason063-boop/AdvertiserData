import pandas as pd
workbook = pd.ExcelFile('C:/仓库/Antigravity-Manager/账单/uploads/weason_20260515055508404576_42004b45_工作簿4.xlsx')
for sheet in workbook.sheet_names:
    print(f'Sheet: {sheet}')
    try:
        df = pd.read_excel(workbook, sheet_name=sheet, nrows=5)
        if '月份归属' in df.columns:
            print(f'月份归属 values: {df["月份归属"].tolist()}')
            for val in df["月份归属"].dropna():
                print(f'val: {val}, type: {type(val)}')
    except Exception as e:
        print(f'Error: {e}')
