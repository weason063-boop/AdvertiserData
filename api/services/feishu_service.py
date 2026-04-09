import logging
import sys
from pathlib import Path

# Ensure project root (账单/) is on sys.path for bare imports
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fetch_feishu_contracts import (
    get_tenant_access_token, 
    resolve_wiki_token, 
    fetch_sheet_valus,
    APP_ID, APP_SECRET, APP_TOKEN
)
from api.migrate import migrate_feishu_contract_lines

logger = logging.getLogger(__name__)

class FeishuService:
    def sync_contracts(self) -> dict:
        """
        同步飞书合同条款到数据库
        """
        logger.info("Starting Feishu contract sync...")
        
        # 1. Get Access Token
        token = get_tenant_access_token(APP_ID, APP_SECRET)
        if not token:
            logger.error("Failed to get Feishu access token")
            return {"status": "error", "message": "无法获取飞书 Access Token"}
            
        real_app_token = APP_TOKEN
        
        # 2. Resolve Wiki Token if needed
        if len(APP_TOKEN) > 20: 
            obj_type, obj_token = resolve_wiki_token(token, APP_TOKEN)
            if obj_type == 'sheet':
                real_app_token = obj_token
                logger.info(f"Resolved Wiki Token to Sheet Token: {real_app_token}")
            elif obj_type == 'bitable':
                logger.warning("Bitable type resolved but not yet supported in this sync service.")
                # Future: Support Bitable
                pass

        # 3. Fetch Data
        values = fetch_sheet_valus(token, real_app_token)
        if not values:
             return {"status": "error", "message": "飞书表格为空或无法读取"}
             
        # 4. Parse Data
        if len(values) < 2:
            return {"status": "error", "message": "飞书表格数据行数不足"}
            
        headers = values[0]
        data_start_index = 1

        # Merge with second row only when row2 still looks like header.
        if len(values) > 1:
            headers2 = values[1]
            row2_text = ''.join(str(x) for x in headers2 if x)
            header_markers = ['客户', '简称', '服务费', '业务类型', '执行部门']
            row2_is_header = any(marker in row2_text for marker in header_markers)
            if row2_is_header:
                merged_headers = []
                for i in range(max(len(headers), len(headers2))):
                    h1 = str(headers[i]) if i < len(headers) and headers[i] else ""
                    h2 = str(headers2[i]) if i < len(headers2) and headers2[i] else ""
                    # Combine or pick the non-empty one
                    merged_headers.append(f"{h1}{h2}".strip())
                headers = merged_headers
                data_start_index = 2

        logger.info("Feishu merged headers: %s", headers)
        
        try:
            name_idx = headers.index('客户简称')
        except ValueError:
            # Try fuzzy match for "简称"
            name_idx = -1
            for i, h in enumerate(headers):
                if h and '客户简称' in str(h):
                    name_idx = i
                    break
            if name_idx == -1:
                return {"status": "error", "message": "表格缺少必要列: '客户简称'"}
        
        # Optional columns
        def get_col_index(name):
            try:
                return headers.index(name)
            except ValueError:
                # Fuzzy match
                for i, h in enumerate(headers):
                    if h and name in str(h):
                        return i
                return -1
                
        type_idx = get_col_index('业务类型')
        dept_idx = get_col_index('执行部门')
        entity_idx = get_col_index('主体')  # Match '主体' or '客户主体'
        term_idx = get_col_index('服务费')
        payment_term_idx = get_col_index('账期')
        
        if term_idx == -1:
            return {"status": "error", "message": "表格缺少 '服务费' 条款列，无法同步"}

        logger.info(
            "Feishu column indices: name=%s, entity=%s, payment_term=%s, fee=%s",
            name_idx, entity_idx, payment_term_idx, term_idx
        )
        
        data_to_migrate = []
        for row_index, row in enumerate(values[data_start_index:], start=data_start_index + 1):
            if not row or len(row) <= name_idx:
                continue
                
            name = row[name_idx]
            if not name:
                continue
                
            def get_val(idx):
                if idx >= 0 and idx < len(row):
                    return row[idx]
                return None
            
            entry = {
                'name': name,
                'business_type': get_val(type_idx),
                'department': get_val(dept_idx),
                'entity': get_val(entity_idx),
                'fee_clause': get_val(term_idx),
                'payment_term': get_val(payment_term_idx),
                '_source_row_index': row_index,
            }
            if len(data_to_migrate) < 5:
                logger.info("Feishu sync sample entry: %s", entry)
            data_to_migrate.append(entry)
            
        # 5. Update Database (line-level storage + deterministic aggregation)
        try:
            sync_stats = migrate_feishu_contract_lines(
                data_to_migrate,
                source_token=real_app_token,
                source_type="feishu_sheet",
            )
        except Exception as exc:
            logger.exception("Failed while migrating Feishu rows")
            return {"status": "error", "message": str(exc)}
        client_count = sync_stats.get("client_count", 0)
        line_count = sync_stats.get("line_count", 0)
        
        return {
            "status": "ok", 
            "message": f"成功同步 {line_count} 条飞书原始行，聚合 {client_count} 条客户条款",
            "count": client_count,
            "line_count": line_count,
            "client_count": client_count
        }
