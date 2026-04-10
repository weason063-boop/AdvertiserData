# -*- coding: utf-8 -*-
"""
条款解析模块

负责解析服务费条款文本，提取费率和固定费用。
支持: 阶梯费率、固定+比例、范围固定费、月费等 9 种匹配模式。
"""

import logging
import re
from datetime import datetime
from typing import Tuple, Optional

import pandas as pd

from .client_overrides import apply_pre_overrides

logger = logging.getLogger(__name__)


# =============================================================================
# 媒介关键词映射
# =============================================================================

MEDIA_KEYWORDS = {
    'Google': ['GG', 'Google', 'google'],
    'TikTok': ['TT', 'TikTok', 'Tiktok'],
    'Tiktok': ['TT', 'TikTok', 'Tiktok'],
    'Meta': ['FB', 'Facebook', 'Meta'],
    'Facebook': ['FB', 'Facebook', 'Meta'],
    'Taboola': ['Taboola'],
    'Yahoo': ['Yahoo', 'yahoo'],
    'TTD': ['TTD'],
    'Pinterest': ['Pinterest'],
    'Linkedin': ['Linkedin', 'LinkedIn'],
    'Reddit': ['Reddit'],
    'Naver': ['Naver'],
    'Yandex': ['yandex', 'Yandex'],
    'Bing': ['Bing', 'BING'],
    'YouTube': ['YOUTUBE', 'Youtube', 'youtube'],
    '直采资源': ['直采', '直采资源'],
    'DOOH数字户外广告': ['DOOH', 'DOOH数字户外广告'],
    'Uber': ['Uber'],
}

ALL_MEDIA_KEYWORDS = set()
for _k_list in MEDIA_KEYWORDS.values():
    ALL_MEDIA_KEYWORDS.update(_k_list)


def _extract_media_segment(line, target_keywords):
    """
    当一行包含多个媒介关键词时，提取目标媒介所属的子段落。
    避免跨媒介正则误匹配。

    例如: line = "GG 1000+FB 1000+TT 500+10%"
      target_keywords=['FB','Facebook','Meta'] → "FB 1000"
      target_keywords=['TT','TikTok']          → "TT 500+10%"
    """
    line_lower = line.lower()
    target_kw_set = {kw.lower() for kw in target_keywords}

    # 找到目标媒介关键词在行中的最早位置
    target_pos = len(line)
    target_kw_end = target_pos
    for kw in target_keywords:
        idx = line_lower.find(kw.lower())
        if 0 <= idx < target_pos:
            target_pos = idx
            target_kw_end = idx + len(kw)

    if target_pos >= len(line):
        return None

    # 找到目标关键词之后、最近的其他媒介关键词位置
    next_media_pos = len(line)
    for kw_list in MEDIA_KEYWORDS.values():
        for kw in kw_list:
            if kw.lower() in target_kw_set:
                continue
            idx = line_lower.find(kw.lower(), target_kw_end)
            if 0 <= idx < next_media_pos:
                # 检查 target_kw_end 和 idx 之间是否只有标点/分隔符
                text_between = line[target_kw_end:idx]
                clean_text = re.sub(r'[\s\+＋、，,。/\|&和及与]', '', text_between)
                if not clean_text:
                    # 如果只有分隔符，说明它们是紧连着的并排媒介（例: GG、TT），属于同一费率组，不应在此截断
                    continue
                next_media_pos = idx

    segment = line[target_pos:next_media_pos].strip()
    # 去掉尾部用作段落分隔的 +
    segment = segment.rstrip('+＋').strip()
    return segment if segment else None


# =============================================================================
# 时间感知条款提取
# =============================================================================

def extract_applicable_clause(clause: str, target_date_str: str) -> str:
    """
    从包含多个时间段的条款中提取适用于目标日期的子条款

    例如:
      "GG 8%。2025年9月起 FB、TTD 5%。"
      → 如果目标日期是2026年1月，返回 "FB、TTD 5%。"（9月起的条款）
    """
    year_month_match = re.search(r'(\d{4})[年\-](\d{1,2})', target_date_str)
    if not year_month_match:
        return clause

    target_year = int(year_month_match.group(1))
    target_month = int(year_month_match.group(2))
    target_date = datetime(target_year, target_month, 1)

    time_pattern = r'((?:20)?\d{2,4}年)?(\d{1,2})月起'
    parts = re.split(time_pattern, clause)

    base_clause = ""
    if parts and parts[0]:
        base_clause = parts[0].strip()

    segments = []
    i = 1
    while i < len(parts):
        if i + 2 < len(parts):
            year_str = parts[i]
            month_str = parts[i + 1]
            seg_clause = parts[i + 2]

            if year_str:
                year_str = year_str.replace('年', '').strip()
                if len(year_str) == 2:
                    year = 2000 + int(year_str)
                else:
                    year = int(year_str)
            else:
                year = target_year

            month = int(month_str)
            seg_date = datetime(year, month, 1)

            next_time_match = re.search(time_pattern, seg_clause)
            if next_time_match:
                seg_clause_clean = seg_clause[:next_time_match.start()].strip()
            else:
                seg_clause_clean = seg_clause.strip()

            segments.append({
                'date': seg_date,
                'clause': seg_clause_clean,
                'year': year,
                'month': month
            })
            i += 3
        else:
            break

    applicable_segments = [s for s in segments if s['date'] <= target_date]

    if applicable_segments:
        applicable_segments.sort(key=lambda x: x['date'], reverse=True)
        return applicable_segments[0]['clause']
    else:
        return base_clause


# =============================================================================
# 阶梯费率解析
# =============================================================================

def parse_tiered_from_text(text: str, consumption: float) -> Optional[Tuple[float, float]]:
    """
    从文本中解析阶梯费率，返回对应消耗金额的 (比例, 固定) 或 None

    支持格式:
      - 0＜X≤3w，10%；X>3w，8%
      - x≤10000, 1000；X>10000,10%
      - X≤2W，1000；2W<X≤4W，1500
      - 0<X<50000，12%；50000<X<150000，10%；X>150000，8%
    """
    # 统一替换全角符号
    text = text.replace('＜', '<').replace('＞', '>').replace('，', ',').replace('；', ';')
    text = text.replace('≤', '<=').replace('≥', '>=').replace('≦', '<=').replace('≧', '>=')
    text = text.replace('x', 'X')

    def _resolve_threshold(val: float, unit: str, text: str) -> float:
        if unit in ['w', 'W', '万']:
            return val * 10000
        if val < 1000 and re.search(r'[wW万]', text):
            return val * 10000
        return val

    op_pat = r'(?:<=|>=|[<>])'

    # 格式A: 双向范围 "数字 op X op 数字(w), 值(%)"
    double_tiers = re.findall(
        r'(\d+(?:\.\d+)?)\s*(' + op_pat + r')\s*X\s*(' + op_pat + r')\s*(\d+(?:\.\d+)?)\s*([wW万])?\s*[,]?\s*(\d+(?:\.\d+)?)\s*(%)?',
        text
    )

    for low_s, low_op, high_op, high_s, unit, val_s, pct in double_tiers:
        low = _resolve_threshold(float(low_s), unit, text)
        high = _resolve_threshold(float(high_s), unit, text)
        value = float(val_s)

        low_pass = (consumption > low) if '<' in low_op and '=' not in low_op else (consumption >= low)
        high_pass = (consumption < high) if '<' in high_op and '=' not in high_op else (consumption <= high)

        if low_pass and high_pass:
            if pct == '%':
                return (value / 100, 0.0)
            else:
                return (0.0, value)

    # 格式B: 单向 "X op 数字(w), 值(%)"
    single_tiers = re.findall(
        r'X\s*(' + op_pat + r')\s*(\d+(?:\.\d+)?)\s*([wW万])?\s*[,]?\s*(\d+(?:\.\d+)?)\s*(%)?',
        text
    )

    for op, threshold_s, unit, val_s, pct in single_tiers:
        threshold = _resolve_threshold(float(threshold_s), unit, text)
        value = float(val_s)

        matched = False
        if '<' in op:
            if '=' in op: matched = (consumption <= threshold)
            else: matched = (consumption < threshold)
        elif '>' in op:
            if '=' in op: matched = (consumption >= threshold)
            else: matched = (consumption > threshold)

        if matched:
            if pct == '%':
                return (value / 100, 0.0)
            else:
                return (0.0, value)

    # 格式C: 反向 "数字(w) op X, 值(%)"
    reverse_tiers = re.findall(
        r'(\d+(?:\.\d+)?)\s*([wW万])?\s*(' + op_pat + r')\s*X\s*[,]?\s*(\d+(?:\.\d+)?)\s*(%)?',
        text
    )

    for threshold_s, unit, op, val_s, pct in reverse_tiers:
        threshold = _resolve_threshold(float(threshold_s), unit, text)
        value = float(val_s)

        matched = False
        if '<' in op:
            if '=' in op: matched = (consumption >= threshold)
            else: matched = (consumption > threshold)
        elif '>' in op:
            if '=' in op: matched = (consumption <= threshold)
            else: matched = (consumption < threshold)

        if matched:
            if pct == '%':
                return (value / 100, 0.0)
            else:
                return (0.0, value)

    # 格式D: "超过Xw，Y%"
    over_match = re.search(r'超过\s*(\d+(?:\.\d+)?)\s*([wW万])?\s*[,]?\s*(\d+(?:\.\d+)?)\s*%', text)
    if over_match:
        threshold = float(over_match.group(1))
        if over_match.group(2) in ['w', 'W', '万']:
            threshold *= 10000
        if consumption > threshold:
            return (float(over_match.group(3)) / 100, 0.0)

    return None


# =============================================================================
# 核心条款解析
# =============================================================================

def parse_fee_clause(
    clause: str,
    media: str,
    service_type: str,
    consumption: float = 0,
    combined_consumption: float = None,
    calculation_date: str = None,
    client_name: str = ''
) -> Tuple[float, float]:
    """
    解析服务费条款，返回 (比例费率, 固定费用)

    匹配优先级 (P1-P9):
      P1: 固定+阶梯    P2: 合计基础固定+比例   P3: 各X+比例
      P4: 阶梯费率      P5: 范围固定费          P6: 金额+百分比
      P7: 直接百分比    P8: 范围固定费(简写)    P9: /月固定费
    """
    media_text = str(media or '').strip()
    if '直采资源' in media_text or media_text == '直采':
        return (0.05, 0.0)

    if pd.isna(clause) or str(clause).strip() in ['无', '0', '', '0.0']:
        return (0.0, 0.0)

    clause = str(clause).strip()
    clause = clause.replace('％', '%').replace('﹪', '%')

    # 客户特殊规则覆盖
    clause, service_type, early_result = apply_pre_overrides(clause, media, service_type, client_name)
    if early_result is not None:
        return early_result

    # 特殊条款直接返回0
    special_keywords = ['代运营条款', '众筹条款', '自营项目', '项目制', '视频条款', '社媒条款',
                        '无代投服务费', '跟项目一并收取', '从视频条款', '从代运营条款',
                        '随代运营', '广告费合并报价', 'ROAS', '抽佣', '代投无单独服务费']
    for sk in special_keywords:
        if sk in clause:
            return (0.0, 0.0)

    # 时间感知条款提取
    if calculation_date:
        clause = extract_applicable_clause(clause, calculation_date)

    # 获取当前媒介关键词
    keywords = MEDIA_KEYWORDS.get(media, [media])
    type_kw = '流水' if service_type == '流水' else '代投'
    check_consumption = combined_consumption if combined_consumption is not None else consumption

    # 规则2: 只有Google流水才有服务费
    if service_type == '流水' and media != 'Google':
        has_media_liushui = False
        for kw in keywords:
            if f'{kw}流水' in clause:
                has_media_liushui = True
                break
        if not has_media_liushui:
            return (0.0, 0.0)

    # 按行拆分
    lines = re.split(r'[;,\n；。，]', clause)
    lines = [l.strip() for l in lines if l.strip()]
    if len(lines) == 1:
        lines = [clause]

    # 先尝试精确匹配流水相关模式
    for line in lines:
        for kw in keywords:
            escaped_kw = re.escape(str(kw))
            zero_match = re.search(rf'{escaped_kw}\s*流水\s*(?:服务费)?\s*0(?![\\d.])', line)
            if zero_match and service_type == '流水':
                return (0.0, 0.0)

            liushui_pct = re.search(rf'{escaped_kw}\s*流水\s*(?:服务费)?\s*(\d+(?:\.\d+)?)\s*%', line)
            if liushui_pct and service_type == '流水':
                return (float(liushui_pct.group(1)) / 100, 0.0)

            liushui_tier = re.search(rf'{escaped_kw}\s*流水\s*(?:服务费)?\s*X', line)
            if liushui_tier and service_type == '流水':
                result = parse_tiered_from_text(line, check_consumption)
                if result:
                    return result

    # 流水类型回退
    if service_type == '流水':
        # Support compact media-specific clauses like "GG1%".
        for kw in keywords:
            compact_media_pct = re.search(
                rf'{re.escape(kw)}(?:[^\d%]|\s)*(\d+(?:\.\d+)?)\s*%',
                clause,
                re.IGNORECASE
            )
            if compact_media_pct:
                return (float(compact_media_pct.group(1)) / 100, 0.0)

        generic_pct = re.search(r'(?:服务费|消耗)\s*(\d+(?:\.\d+)?)\s*%', clause)
        if generic_pct:
            if '代投' in clause and '流水' not in clause:
                return (0.0, 0.0)
            return (float(generic_pct.group(1)) / 100, 0.0)

        if re.fullmatch(r'0\.\d+', clause.strip()):
            if '代投' not in clause:
                return (float(clause.strip()), 0.0)

        return (0.0, 0.0)

    # 单渠道条款优先
    if '单个渠道' in clause or '单渠道' in clause:
        tier_result = parse_tiered_from_text(clause, check_consumption)
        if tier_result:
            return tier_result
        range_match = re.search(r'(\d+)\s*[-~−–]\s*(\d+)[wW万]\s*[，,]?\s*(?:服务费)?\s*(\d+)(?!\s*%)', clause)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2)) * 10000
            fixed_fee = float(range_match.group(3))
            if low <= check_consumption <= high:
                return (0.0, fixed_fee)
        over_match = re.search(r'超过\s*(\d+)[wW万]?\s*[，,]?\s*(\d+(?:\.\d+)?)\s*%', clause)
        if over_match:
            threshold = float(over_match.group(1))
            if 'w' in clause.lower() or '万' in clause:
                threshold *= 10000
            if check_consumption > threshold:
                return (float(over_match.group(2)) / 100, 0.0)

    # 上下文状态追踪（多行多媒介条款）
    active_media_context = False

    for line in lines:
        contains_target = any(kw.lower() in line.lower() for kw in keywords)

        contains_other = False
        if not contains_target:
            for kw in ALL_MEDIA_KEYWORDS:
                if kw in keywords:
                    continue
                if kw.lower() in line.lower():
                    contains_other = True
                    break

        if contains_target:
            active_media_context = True
        elif contains_other:
            active_media_context = False

        if not active_media_context and not contains_target:
            has_any_media = any(kw.lower() in clause.lower() for kw in ALL_MEDIA_KEYWORDS)
            if has_any_media:
                continue

        if '流水' in line and '代投' not in line and service_type == '代投':
            continue
        if '代投' in line and '流水' not in line and service_type == '流水':
            continue

        # 多媒介行段落提取：当同一行包含目标媒介和其他媒介时，
        # 仅提取目标媒介所属的子段落，避免跨媒介正则误匹配
        match_text = line
        if contains_target:
            _has_other_in_line = any(
                kw.lower() in line.lower()
                for kw in ALL_MEDIA_KEYWORDS
                if kw not in keywords
            )
            if _has_other_in_line:
                segment = _extract_media_segment(line, keywords)
                if segment:
                    match_text = segment

        # P1: 固定+阶梯
        fixed_plus_tier = re.search(r'固定\s*(\d+)\s*\+', match_text)
        if fixed_plus_tier:
            fixed_val = float(fixed_plus_tier.group(1))
            tier_result = parse_tiered_from_text(match_text, check_consumption)
            if tier_result:
                return (tier_result[0], fixed_val + tier_result[1])
            return (0.0, fixed_val)

        # P2: 合计基础固定+比例
        combined_fixed_pct = re.search(r'[合计基础]+\s*(\d+(?:\.\d+)?)\s*[+＋]\s*(?:消耗\s*[*×]?\s*)?(\d+(?:\.\d+)?)\s*%', match_text)
        if combined_fixed_pct:
            return (float(combined_fixed_pct.group(2)) / 100, float(combined_fixed_pct.group(1)))

        # P3: 各X+比例
        per_media_fixed_pct = re.search(r'各\s*(\d+)\s*[+＋]\s*(?:消耗\s*[*×]?\s*)?(\d+(?:\.\d+)?)\s*%', match_text)
        if per_media_fixed_pct:
            return (float(per_media_fixed_pct.group(2)) / 100, float(per_media_fixed_pct.group(1)))

        # P4: 阶梯费率
        if re.search(r'[<>≤≥＜＞]\s*X|X\s*[<>≤≥＜＞]', match_text):
            # 多媒介行时仅解析当前媒介段落；单媒介行保持原逻辑使用完整条款
            tier_source = match_text if match_text != line else clause
            tier_result = parse_tiered_from_text(tier_source, check_consumption)
            if tier_result:
                return tier_result

        # P5: 范围固定费
        range_fixed = re.findall(r'(\d+(?:\.\d+)?)[wW万]?\s*[<＜]\s*X\s*[≤＜<]\s*(\d+(?:\.\d+)?)[wW万]?\s*[，,]\s*(\d+)(?!\s*%)', match_text)
        if range_fixed:
            for low_s, high_s, val_s in range_fixed:
                low = float(low_s)
                high = float(high_s)
                if 'w' in match_text.lower() or '万' in match_text:
                    low *= 10000
                    high *= 10000
                val = float(val_s)
                if low < check_consumption <= high:
                    return (0.0, val)

        # P6: 金额+百分比
        amt_pct = re.search(r'(?:^|[^0-9])(\d+)\s*[+＋]\s*(?:消耗\s*[*×]?\s*)?(\d+(?:\.\d+)?)\s*%', match_text)
        if amt_pct:
            pos = amt_pct.start(1)
            if pos > 0 and match_text[pos-1] in ['w', 'W', '万']:
                pass
            else:
                return (float(amt_pct.group(2)) / 100, float(amt_pct.group(1)))

        # P7: 直接百分比
        has_tier_indicator = bool(re.search(r'[<>≤≥＜＞]|超过|[-~−–]\d+[wW万]', match_text))
        if not has_tier_indicator:
            direct_pct = re.findall(r'(\d+(?:\.\d+)?)\s*%', match_text)
            if direct_pct:
                return (float(direct_pct[0]) / 100, 0.0)

        # P8: 范围固定费（简写）
        range_simple = re.search(r'(\d+)\s*[-~−–]\s*(\d+)[wW万]\s*[，,]?\s*(?:服务费)?\s*(\d+)(?!\s*%)', match_text)
        if range_simple:
            low = float(range_simple.group(1))
            high = float(range_simple.group(2)) * 10000
            val = float(range_simple.group(3))
            if low <= check_consumption <= high:
                return (0.0, val)

        # P9: /月 固定费
        monthly = re.search(r'(\d+)\s*/\s*月', match_text)
        if monthly and contains_target:
            return (0.0, float(monthly.group(1)))

        # P10: 独立固定费（从多媒介段落中提取的纯数字固定费，如 "FB 1000"）
        if contains_target and match_text != line:
            if not re.search(r'%|/\s*月|[<>≤≥＜＞]', match_text):
                standalone_fixed = re.search(r'(\d+(?:\.\d+)?)\s*$', match_text)
                if standalone_fixed:
                    val = float(standalone_fixed.group(1))
                    if val > 0:
                        return (0.0, val)

    # 全局回退模式
    if '单个渠道' in clause or '单渠道' in clause:
        range_match = re.search(r'(\d+)\s*[-~]\s*(\d+)[wW万]\s*[，,]?\s*(?:服务费)?\s*(\d+)', clause)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2)) * 10000
            fixed_fee = float(range_match.group(3))
            if low <= check_consumption <= high:
                return (0.0, fixed_fee)

        over_match = re.search(r'超过\s*(\d+)[wW万]?\s*[，,]?\s*(\d+(?:\.\d+)?)\s*%', clause)
        if over_match:
            threshold = float(over_match.group(1))
            if 'w' in clause.lower() or '万' in clause:
                threshold *= 10000
            if check_consumption > threshold:
                return (float(over_match.group(2)) / 100, 0.0)

    if service_type == '代投':
        daitou_pct = re.search(r'代投\s*(\d+(?:\.\d+)?)\s*%', clause)
        if daitou_pct:
            return (float(daitou_pct.group(1)) / 100, 0.0)

        daitou_fixed_pct = re.search(r'代投\s*(\d+)\s*[+＋]\s*(\d+(?:\.\d+)?)\s*%', clause)
        if daitou_fixed_pct:
            return (float(daitou_fixed_pct.group(2)) / 100, float(daitou_fixed_pct.group(1)))

    generic_consumption = re.search(r'消耗\s*(\d+(?:\.\d+)?)\s*%', clause)
    if generic_consumption:
        return (float(generic_consumption.group(1)) / 100, 0.0)

    generic_fee = re.search(r'服务费\s*(\d+(?:\.\d+)?)\s*%', clause)
    if generic_fee:
        return (float(generic_fee.group(1)) / 100, 0.0)

    if re.fullmatch(r'0\.\d+', clause.strip()):
        return (float(clause.strip()), 0.0)

    standalone_pct = re.fullmatch(r'(\d+(?:\.\d+)?)\s*%\s*[。.]?', clause.strip())
    if standalone_pct:
        return (float(standalone_pct.group(1)) / 100, 0.0)

    return (0.0, 0.0)
