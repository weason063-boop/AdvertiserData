# -*- coding: utf-8 -*-
"""
合同条款加载模块

支持三种数据源:
1. Excel 文件
2. SQLite 数据库
3. 飞书多维表格
"""

import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _is_ad_business_type(business_type) -> bool:
    """
    判断业务类型是否属于广告业务。
    支持中文“广告*”及常见英文值（Ad/Ads/Advertising）。
    """
    if business_type is None:
        return False

    bt = str(business_type).strip()
    if not bt:
        return False

    bt_lower = bt.lower()
    return ('广告' in bt) or (bt_lower in {'ad', 'ads', 'advertising'})


def load_contract_terms(contract_path: str) -> Dict[str, str]:
    """从Excel加载合同条款 → {客户简称: 服务费条款}"""
    df = pd.read_excel(contract_path)

    has_business_type = '业务类型' in df.columns

    terms = {}
    for index, row in df.iterrows():
        customer = row['客户简称']
        clause = row.iloc[-1]
        business_type = row['业务类型'] if has_business_type else None

        # 仅广告业务参与服务费计算
        if has_business_type and not _is_ad_business_type(business_type):
            continue

        if pd.notna(customer):
            key = str(customer).strip()
            clause_val = str(clause).strip() if pd.notna(clause) else '无'

            if key not in terms or (terms[key] == '无' and clause_val != '无'):
                terms[key] = clause_val

    return terms


def load_contract_terms_from_db(db_path: Path = None) -> Dict[str, str]:
    """从 SQLite 数据库加载合同条款"""
    if db_path is None:
        db_path = Path(__file__).parent.parent / "contracts.db"

    if not db_path.exists():
        return {}

    rows = []
    last_error = None
    for attempt in range(3):
        conn = None
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            rows = conn.execute("SELECT name, business_type, fee_clause FROM clients").fetchall()
            last_error = None
            break
        except sqlite3.Error as exc:
            last_error = exc
            logger.warning(
                "读取合同数据库失败(第 %s 次): %s",
                attempt + 1,
                exc
            )
            time.sleep(0.2 * (attempt + 1))
        finally:
            if conn is not None:
                conn.close()

    if last_error is not None:
        logger.error("读取合同数据库失败，回退为空条款集: %s", last_error)
        return {}

    terms = {}
    for name, business_type, clause in rows:
        # 仅广告业务参与服务费计算
        if not _is_ad_business_type(business_type):
            continue
        if name:
            terms[str(name).strip()] = clause if clause else '无'

    return terms


def extract_date_from_filename(filename: str) -> Optional[str]:
    """从文件名提取日期，如 '2026年1月消耗明细.xlsx' → '2026年1月'"""
    match = re.search(r'(\d{4})年(\d{1,2})月', filename)
    if match:
        return f"{match.group(1)}年{match.group(2)}月"
    return None


def load_contract_terms_from_feishu(app_id: str, app_secret: str, app_token: str) -> Dict[str, str]:
    """从飞书加载合同条款 (针对 S 列)"""
    try:
        from fetch_feishu_contracts import get_tenant_access_token, resolve_wiki_token, fetch_sheet_valus
    except ImportError:
        logger.error("Error: fetch_feishu_contracts.py module not found.")
        return {}

    token = get_tenant_access_token(app_id, app_secret)
    if not token:
        return {}

    real_app_token = app_token
    if len(app_token) > 20:
        obj_type, obj_token = resolve_wiki_token(token, app_token)
        if obj_type == 'sheet':
            real_app_token = obj_token

    values = fetch_sheet_valus(token, real_app_token)
    if not values:
        return {}

    terms = {}
    if len(values) > 1:
        headers = values[0]
        if len(values) > 1:
            headers2 = values[1]
            merged_headers = []
            for i in range(max(len(headers), len(headers2))):
                h1 = str(headers[i]) if i < len(headers) and headers[i] else ""
                h2 = str(headers2[i]) if i < len(headers2) and headers2[i] else ""
                merged_headers.append(f"{h1}{h2}".strip())
            headers = merged_headers

        try:
            cust_idx = headers.index('客户简称')
        except ValueError:
            cust_idx = 0

        business_type_idx = -1
        for i, h in enumerate(headers):
            if h and str(h).strip() == '业务类型':
                business_type_idx = i
                break

        term_idx = -1
        for i, h in enumerate(headers):
            if h and "服务费" in str(h):
                term_idx = i
                break

        if term_idx == -1:
            term_idx = 18

        logger.debug(f"Using feishu column {term_idx} ('{headers[term_idx]}' if exists)")

        for row in values[2:]:
            if not row or len(row) <= cust_idx:
                continue

            customer = row[cust_idx]
            business_type = row[business_type_idx] if (business_type_idx >= 0 and len(row) > business_type_idx) else None
            clause = row[term_idx] if len(row) > term_idx else '无'

            # 仅广告业务参与服务费计算（存在业务类型列时）
            if business_type_idx >= 0 and not _is_ad_business_type(business_type):
                continue

            if customer:
                key = str(customer).strip()
                clause_val = str(clause).strip() if clause else '无'

                if key not in terms or (terms[key] == '无' and clause_val != '无'):
                    terms[key] = clause_val

    logger.info(f"Loaded {len(terms)} contract terms from Feishu (using index {term_idx}).")
    return terms
