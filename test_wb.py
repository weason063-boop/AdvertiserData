import pandas as pd
from api.services.calculation_service import CalculationService
srv = CalculationService()
workbook = srv._open_excel_workbook('工作簿3.xlsx', context='消耗上传文件')
for sheet in workbook.sheet_names:
    print(f'Sheet name: {sheet}')
    header_df = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
    columns = [str(col).strip() for col in header_df.columns.tolist()]
    cols = set(columns)
    if not {'母公司', '媒介'}.issubset(cols):
        print('  Skipped (not consumption sheet)')
        continue
    is_client = srv._is_client_account_managed_sheet(sheet, columns)
    print(f'  is_client: {is_client}')
    if not is_client:
        month = srv._parse_month_from_filename(sheet, prefer_latest_match=True)
        print(f'  extracted month: {month}')
        print(f'  has_month_column: {"月份归属" in cols}')
