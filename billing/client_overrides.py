# -*- coding: utf-8 -*-
"""
客户特殊规则加载与应用

从 client_overrides.json 加载客户特殊计费规则，
避免在计算引擎中硬编码客户名。
"""

import json
import logging
import re
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# 默认路径：项目根目录下的 client_overrides.json
_DEFAULT_OVERRIDES_PATH = Path(__file__).parent.parent / "client_overrides.json"

# 模块级缓存
_CLIENT_OVERRIDES = {}
_POST_CALC_OVERRIDES = {}
_LABEL_ALIASES = {}
_LOADED = False


def load_client_overrides(path: Path = None):
    """从 client_overrides.json 加载客户特殊规则"""
    global _CLIENT_OVERRIDES, _POST_CALC_OVERRIDES, _LABEL_ALIASES, _LOADED
    overrides_path = path or _DEFAULT_OVERRIDES_PATH

    if overrides_path.exists():
        try:
            with open(overrides_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _CLIENT_OVERRIDES = data.get('overrides', {})
            _POST_CALC_OVERRIDES = data.get('post_calculation_overrides', {})
            _LABEL_ALIASES = data.get('label_aliases', {})
            _LOADED = True
            logger.info(f"已加载 {len(_CLIENT_OVERRIDES)} 条客户特殊规则")
        except Exception as e:
            logger.warning(f"加载 client_overrides.json 失败: {e}")
    else:
        logger.info("未找到 client_overrides.json，所有客户使用标准条款解析")
        _LOADED = True


def _ensure_loaded():
    """确保配置已加载（惰性初始化）"""
    if not _LOADED:
        load_client_overrides()


def _normalize_media_key(media: str) -> str:
    """Normalize media labels for deterministic exact matching."""
    if media is None:
        return ''

    key = str(media).strip().upper()
    if not key:
        return ''

    aliases = {
        'TT': 'TIKTOK',
        'TIKTOK': 'TIKTOK',
        'TTD': 'TTD',
        'FB': 'FACEBOOK',
        'FACEBOOK': 'FACEBOOK',
        'META': 'FACEBOOK',
        'GG': 'GOOGLE',
        'GOOGLE': 'GOOGLE',
    }
    return aliases.get(key, key)


def apply_pre_overrides(
    clause: str, media: str, service_type: str, client_name: str
) -> Tuple[str, str, Optional[Tuple[float, float]]]:
    """
    应用客户特殊规则（前置），返回 (修改后的条款, 修改后的服务类型, 直接返回结果或None)
    """
    _ensure_loaded()
    normalized_media = _normalize_media_key(media)

    for keyword, rule in _CLIENT_OVERRIDES.items():
        if keyword not in client_name:
            continue

        action = rule.get('action', '')

        if action == 'remove_time_constraint':
            clause = re.sub(r'(?:20)?2\d年\d+月起', '', clause)
            clause = clause.replace('2月起', '')
            force_kw = rule.get('force_keyword', '')
            if force_kw and force_kw not in clause:
                clause = force_kw + ' ' + clause

        elif action == 'force_service_type':
            service_type = rule.get('service_type', service_type)

        elif action == 'conditional_zero':
            cond_kw = rule.get('condition_keyword', '')
            cond_st = rule.get('condition_service_type', '')
            if cond_kw in clause and service_type == cond_st:
                return clause, service_type, (0.0, 0.0)

        elif action == 'fixed_rate':
            rate = rule.get('rate', 0.0)
            return clause, service_type, (rate, 0.0)

        elif action == 'exclude_media':
            excluded = {
                normalized
                for normalized in (
                    _normalize_media_key(item)
                    for item in rule.get('excluded_media', [])
                )
                if normalized
            }
            if normalized_media in excluded:
                return clause, service_type, (0.0, 0.0)

        elif action == 'media_rate':
            r_media = _normalize_media_key(rule.get('media', ''))
            r_st = rule.get('service_type', '')
            r_rate = rule.get('rate', 0.0)
            if r_media == normalized_media and service_type == r_st:
                return clause, service_type, (r_rate, 0.0)

    # 应用标签别名（如 "哇鹅默认" → ""）
    for alias, replacement in _LABEL_ALIASES.items():
        clause = clause.replace(alias, replacement)

    return clause, service_type, None


def apply_post_overrides(
    customer_str: str, fee: float, fixed: float
) -> Tuple[float, float]:
    """
    应用客户特殊规则（后置计算调整）
    """
    _ensure_loaded()

    for keyword, rule in _POST_CALC_OVERRIDES.items():
        if keyword not in customer_str:
            continue
        action = rule.get('action', '')
        if action == 'move_fixed_to_fee' and fixed > 0:
            fee += fixed
            fixed = 0.0
    return fee, fixed

