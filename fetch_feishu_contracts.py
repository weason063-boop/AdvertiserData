import requests
import json
import time

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# 配置信息 (Configuration)
# 请在飞书开放平台创建应用，并获取以下信息
APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN = os.getenv("FEISHU_APP_TOKEN")
TABLE_ID = os.getenv("FEISHU_TABLE_ID")

if not APP_ID or not APP_SECRET:
    print("Warning: FEISHU_APP_ID or FEISHU_APP_SECRET not found in environment variables.")


# Use a session that does not inherit broken system proxy envs.
_SESSION = requests.Session()
_SESSION.trust_env = False


def _http_get(url, headers=None, params=None):
    return _SESSION.get(url, headers=headers, params=params, timeout=30)


def _http_post(url, headers=None, json=None):
    return _SESSION.post(url, headers=headers, json=json, timeout=30)

def get_tenant_access_token(app_id, app_secret):
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    response = _http_post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token")
        else:
            print(f"Error getting token: {data.get('msg')}")
            return None
    else:
        print(f"HTTP Error: {response.status_code}")
        return None

def resolve_wiki_token(token, wiki_token):
    """可以将 wiki token 转换为真实的 obj_token (doc/docx/bitable)"""
    url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={wiki_token}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = _http_get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            node = data.get("data", {}).get("node", {})
            return node.get("obj_type"), node.get("obj_token")
        else:
            print(f"Error resolving wiki token: {data.get('msg')} (Code: {data.get('code')})")
            return None, None
    else:
        print(f"HTTP Error resolving wiki: {response.status_code}")
        print(f"Response: {response.text}")
        return None, None

def list_tables(token, app_token):
    """列出多维表格的所有数据表"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    response = _http_get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("items", [])
        else:
            print(f"Error listing tables: {data.get('msg')}")
            return []
    else:
        print(f"HTTP Error listing tables: {response.status_code}")
        return []

def fetch_records(token, app_token, table_id):
    """获取多维表格记录"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "page_size": 100  # 根据需要调整
    }
    
    response = _http_get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("items", [])
        else:
            print(f"Error fetching records: {data.get('msg')}")
            return []
    else:
        print(f"HTTP Error fetching records: {response.status_code}")
        return []

def fetch_sheet_valus(token, spreadsheet_token):
    """获取电子表格数据 (读取第一个 Sheet 的全部内容)"""
    # 1. 获取表格元数据，找到第一个 sheetId
    meta_url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = _http_get(meta_url, headers=headers)
    
    first_sheet_id = None
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            sheets = data.get("data", {}).get("sheets", [])
            if sheets:
                first_sheet_id = sheets[0].get("sheet_id")
                # print(f"Found {len(sheets)} sheets. Reading first sheet: {sheets[0].get('title')} (ID: {first_sheet_id})")
        else:
             print(f"Error getting sheet meta: {data.get('msg')}")
             return
    else:
        print(f"HTTP Error getting sheet meta: {response.status_code}")
        return

    if not first_sheet_id:
        print("No sheets found in spreadsheet.")
        return

    # 2. 读取数据 (假设不超过 1000 行)
    # Range format: <sheetId>!A1:AZ5000
    # Wider range prevents silently missing rows/columns in large contract sheets.
    range_str = f"{first_sheet_id}!A1:AZ5000"
    data_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range_str}"
    
    response = _http_get(data_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data.get("code") == 0:
            values = data.get("data", {}).get("valueRange", {}).get("values", [])
            # print(f"✅ Successfully fetched {len(values)} rows from Sheet.")
            
            # Print header and first few rows
            # if values:
            #     print(f"Header: {values[0]}")
            #     for i, row in enumerate(values[1:6]):
            #         print(f"Row {i+1}: {row}")
            return values
        else:
            print(f"Error fetching sheet values: {data.get('msg')}")
            if data.get("code") == 4003002:
                print("💡 提示: 您的应用可能缺少 'sheets:spreadsheet:readonly' 权限。")
    else:
        print(f"HTTP Error fetching sheet values: {response.status_code}")

def main():
    if APP_ID == "cli_xxxxxxxx":
        print("请先配置 fetch_feishu_contracts.py 中的 APP_ID 和 APP_SECRET")
        return

    print("Authenticating...")
    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        return
    
    real_app_token = APP_TOKEN
    is_sheet = False
    
    # 1. 尝试解析 Wiki Token
    if len(APP_TOKEN) > 20: 
        print(f"Attempting to resolve Wiki Token: {APP_TOKEN}...")
        obj_type, obj_token = resolve_wiki_token(token, APP_TOKEN)
        
        if obj_type:
            print(f"✅ Resolved Wiki Token -> Type: {obj_type}, Token: {obj_token}")
            
            if obj_type == 'bitable':
                real_app_token = obj_token
            elif obj_type == 'docx':
                 print("⚠️ 检测到这是一个 Docx 文档，而不是多维表格。目前难以结构化读取。")
                 return
            elif obj_type == 'sheet':
                 print("✅ 检测到这是一个电子表格 (Sheet)。切换到 Sheet 读取模式...")
                 real_app_token = obj_token
                 is_sheet = True
        else:
             print("⚠️ Failed to resolve as Wiki Token, trying as direct App Token...")

    if is_sheet:
        res = fetch_sheet_valus(token, real_app_token)
        print(f"Fetched {len(res) if res else 0} rows")
        return

    # 2. 列出所有数据表 (Bitable 模式)
    print(f"\nListing tables for App Token: {real_app_token}...")
    tables = list_tables(token, real_app_token)

    print(f"List tables result: {len(tables)} tables found.")
    
    if not tables:
        return

    print("\n✅ Found the following tables:")
    for t in tables:
        print(f"  - Name: {t.get('name')} | Table ID: {t.get('table_id')}")

    # 如果没有配置 TABLE_ID，默认使用第一个
    target_table_id = TABLE_ID
    if "tbl" not in target_table_id:
        if tables:
            target_table_id = tables[0].get('table_id')
            print(f"\n⚠️ 未配置 TABLE_ID，默认使用第一个表: {tables[0].get('name')} ({target_table_id})")
        else:
            print("No tables found.")
            return

    print(f"\nFetching records from table {target_table_id}...")
    records = fetch_records(token, real_app_token, target_table_id)
    
    print(f"Found {len(records)} records.")
    
    # 打印前5条记录，展示字段结构
    for i, record in enumerate(records[:5]):
        fields = record.get("fields", {})
        print(f"Record {i+1}: {json.dumps(fields, ensure_ascii=False, indent=2)}")

if __name__ == "__main__":
    main()
