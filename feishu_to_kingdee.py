import requests
import json
import time
from datetime import datetime, timedelta

# 配置信息 (从 fetch_feishu_contracts.py 继承)
APP_ID = "cli_a901555a41a15cc5"
APP_SECRET = "yi9tX7n7IiZl8JyvxF6QNA0STH4FqeFR"

class FeishuApprovalClient:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None
        self.token_expiry = 0

    def _get_tenant_access_token(self):
        """获取或刷新 tenant_access_token"""
        if self.token and time.time() < self.token_expiry:
            return self.token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                self.token = data.get("tenant_access_token")
                # 提前 5 分钟刷新
                self.token_expiry = time.time() + data.get("expire", 3600) - 300
                return self.token
        print(f"Auth Error: {resp.text}")
        return None

    def get_approval_definitions(self):
        """获取可见的审批定义列表"""
        token = self._get_tenant_access_token()
        if not token: return []

        url = "https://open.feishu.cn/open-apis/approval/v4/approvals"
        headers = {"Authorization": f"Bearer {token}"}
        
        all_apps = []
        page_token = ""
        while True:
            params = {"page_size": 100, "page_token": page_token}
            resp = requests.get(url, headers=headers, params=params)
            if resp.status_code != 200: break
            
            data = resp.json()
            if data.get("code") != 0: break
            
            items = data.get("data", {}).get("approval_list", [])
            all_apps.extend(items)
            
            page_token = data.get("data", {}).get("page_token")
            if not page_token: break
            
        return all_apps

    def get_approval_instances(self, approval_code, start_time=None, end_time=None):
        """
        获取审批实例列表
        start_time/end_time: 毫秒时间戳
        """
        token = self._get_tenant_access_token()
        if not token: return []

        url = "https://open.feishu.cn/open-apis/approval/v4/instances"
        headers = {"Authorization": f"Bearer {token}"}
        
        all_instances = []
        page_token = ""
        
        # 如果未指定时间，默认获取过去7天
        if not end_time:
            end_time = int(time.time() * 1000)
        if not start_time:
            start_time = end_time - (7 * 24 * 3600 * 1000)

        while True:
            params = {
                "approval_code": approval_code,
                "start_time": str(start_time),
                "end_time": str(end_time),
                "page_size": 100,
                "page_token": page_token
            }
            resp = requests.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                print(f"API Error: {resp.text}")
                break
            
            data = resp.json()
            if data.get("code") != 0:
                print(f"Business Error: {data.get('msg')}")
                break
            
            items = data.get("data", {}).get("instance_list", [])
            all_instances.extend(items)
            
            page_token = data.get("data", {}).get("page_token")
            if not page_token:
                break
                
        return all_instances

    def get_instance_detail(self, instance_id):
        """获取单个审批实例详情，解析表单数据"""
        token = self._get_tenant_access_token()
        if not token: return None

        url = f"https://open.feishu.cn/open-apis/approval/v4/instances/{instance_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data")
        return None

def parse_form_data(form_json_str):
    """
    解析审批表单中的字段
    飞书返回的 form 是一个 JSON 字符串数组
    """
    try:
        form_data = json.loads(form_json_str)
        result = {}
        for item in form_data:
            label = item.get("name")
            value = item.get("value")
            # 记录原始 ID 以防万一
            field_id = item.get("id")
            result[label] = value
        return result
    except Exception as e:
        print(f"Parse error: {e}")
        return {}

class KingdeeConverter:
    def __init__(self, config_path="config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.account_mapping = self.config.get("account_mapping", {})
        self.field_mapping = self.config.get("field_mapping", {})
        self.kingdee_conf = self.config.get("kingdee", {})

    def parse_instance(self, instance, instance_type="payment"):
        """解析单个审批实例"""
        form_data = instance.get("form", [])
        # 如果 form 是字符串，解析它
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
            
        parsed_data = {}
        mapping = self.field_mapping.get(instance_type, {})
        
        # 将 list 用于查找
        form_dict = {}
        for item in form_data:
            form_dict[item.get("name")] = item.get("value")
            if item.get("type") == "fieldList":
                form_dict[item.get("name")] = item.get("value") # Keep list structure

        # 提取基础字段
        for field, target_name in mapping.items():
            if field == "detail_list": continue # 处理明细列表
            parsed_data[field] = form_dict.get(target_name)

        # 特殊处理明细
        if "detail_list" in mapping:
            detail_name = mapping["detail_list"]
            raw_details = form_dict.get(detail_name, [])
            parsed_details = []
            detail_fields = mapping.get("detail_fields", {})
            
            for row in raw_details:
                row_dict = {}
                # row is a list of widgets
                temp_map = {w.get("name"): w.get("value") for w in row}
                for d_field, d_name in detail_fields.items():
                    row_dict[d_field] = temp_map.get(d_name)
                parsed_details.append(row_dict)
            
            parsed_data["details"] = parsed_details
            
        return parsed_data

    def generate_voucher_rows(self, parsed_data, instance_code):
        """生成凭证分录行"""
        rows = []
        
        # 1. 确定日期和期间
        date_str = parsed_data.get("date", "")[:10] # YYYY-MM-DD
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year = dt.year
            period = dt.month
        except:
            year = 2024
            period = 1

        common_base = {
            "凭证日期": date_str,
            "会计年度": year,
            "会计期间": period,
            "凭证字": self.kingdee_conf.get("voucher_word", "记"),
            "凭证号": int(instance_code[-4:]) if instance_code[-4:].isdigit() else 1, # 简单逻辑
            "币别代码": "RMB",
            "币别名称": "人民币",
            "业务日期": date_str,
            "附件数": 1,
            "摘要": parsed_data.get("reason", "")
        }

        # 2. 生成借方分录 (费用/成本)
        if "details" in parsed_data and parsed_data["details"]:
            # 如果有明细，按明细生成多行
            for idx, detail in enumerate(parsed_data["details"]):
                category = detail.get("category", "DEFAULT")
                amount = float(detail.get("amount", 0))
                
                # 查找科目映射
                account_info = self.account_mapping.get(category)
                if not account_info:
                    # 尝试用 key 匹配
                    for k, v in self.account_mapping.items():
                        if k in category:
                            account_info = v
                            break
                    if not account_info:
                        account_info = self.account_mapping.get("DEFAULT", {"code": "6602.99", "name": "其他"})

                row = common_base.copy()
                row.update({
                    "分录号": idx + 1,
                    "摘要": f"{common_base['摘要']} - {category}",
                    "科目代码": account_info.get("code"),
                    "科目名称": account_info.get("name"),
                    "原币金额": amount,
                    "借方金额": amount,
                    "贷方金额": 0
                })
                rows.append(row)
        else:
            # 无明细，生成单行借方
            amount = float(parsed_data.get("amount", 0))
            category = parsed_data.get("reason", "DEFAULT") # 简单用reason做category fallback
            # 这里简化逻辑，实际可能需要更复杂的判断
            account_info = self.account_mapping.get("DEFAULT")
            
            row = common_base.copy()
            row.update({
                "分录号": 1,
                "科目代码": account_info.get("code"),
                "科目名称": account_info.get("name"),
                "原币金额": amount,
                "借方金额": amount,
                "贷方金额": 0
            })
            rows.append(row)

        # 3. 生成贷方分录 (银行存款/应付账款)
        # 贷方通常对应 "银行存款" 或 "其他应付款"
        # 这里为了演示，固定一个贷方科目，实际需配置
        total_amount = sum([r["借方金额"] for r in rows])
        credit_row = common_base.copy()
        credit_row.update({
            "分录号": len(rows) + 1,
            "科目代码": "1002.01", # 示例：银行存款
            "科目名称": "银行存款",
            "原币金额": total_amount,
            "借方金额": 0,
            "贷方金额": total_amount,
            "摘要": f"付: {common_base['摘要']}"
        })
        rows.append(credit_row)
        
        return rows

    def save_to_excel(self, all_rows, output_file="feishu_vouchers.xls"):
        """保存为金蝶兼容的 Excel"""
        import pandas as pd
        
        # 金蝶标准表头 (来自 inspecting template)
        headers = ['凭证日期', '会计年度', '会计期间', '凭证字', '凭证号', '科目代码', '科目名称', '币别代码', '币别名称', '原币金额', '借方金额', '贷方金额', '数量', '单价', '参考信息', '业务日期', '摘要', '核算项目']
        
        df = pd.DataFrame(all_rows)
        # 补全缺失列
        for col in headers:
            if col not in df.columns:
                df[col] = None
        
        # 调整列顺序
        df = df[headers]
        
        # 保存
        df.to_excel(output_file, index=False)
        print(f"Successfully saved {len(df)} rows to {output_file}")

if __name__ == "__main__":
    # Test Mode
    try:
        with open("mock_feishu_data.json", "r", encoding="utf-8") as f:
            mock_data = json.load(f)
        
        converter = KingdeeConverter()
        all_voucher_rows = []
        
        for instance in mock_data:
            # 简单判断类型
            inst_type = "reimbursement" if "报销" in json.dumps(instance) else "payment"
            parsed = converter.parse_instance(instance, inst_type)
            rows = converter.generate_voucher_rows(parsed, instance.get("instance_code"))
            all_voucher_rows.extend(rows)
            
        converter.save_to_excel(all_voucher_rows)
            
    except Exception as e:
        print(f"Test Execution Failed: {e}")
        import traceback
        traceback.print_exc()

    # client = FeishuApprovalClient(APP_ID, APP_SECRET)
    # print("Ready.")
