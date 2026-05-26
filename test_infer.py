import pandas as pd
from api.services.calculation_service import CalculationService
srv = CalculationService()
print('Infer from 工作簿4:', srv._infer_primary_month_from_workbook('C:/仓库/Antigravity-Manager/账单/uploads/weason_20260515055508404576_42004b45_工作簿4.xlsx', '工作簿4.xlsx'))
