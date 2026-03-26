# -*- coding: utf-8 -*-
"""
billing 模块 — 服务费计算引擎

从 calculate_service_fee.py 拆分而来，按职责划分为:
- client_overrides: 客户特殊规则加载与应用
- clause_parser: 条款解析 (正则匹配、阶梯费率)
- contract_loader: 合同条款加载 (飞书/DB/Excel)
- fee_engine: 主计算流程编排
"""

from .fee_engine import calculate_service_fees
from .clause_parser import parse_fee_clause
from .contract_loader import (
    load_contract_terms,
    load_contract_terms_from_db,
    load_contract_terms_from_feishu,
)
from .client_overrides import (
    load_client_overrides,
    apply_pre_overrides,
    apply_post_overrides,
)

__all__ = [
    "calculate_service_fees",
    "parse_fee_clause",
    "load_contract_terms",
    "load_contract_terms_from_db",
    "load_contract_terms_from_feishu",
    "load_client_overrides",
    "apply_pre_overrides",
    "apply_post_overrides",
]
