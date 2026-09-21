# -*- coding: utf-8 -*-
"""
条款解析模块

负责解析服务费条款文本，提取费率和固定费用。
支持: 阶梯费率、固定+比例、范围固定费、月费等 9 种匹配模式。
"""

import logging
import re
from datetime import datetime
from functools import lru_cache
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
    'Google DV360': ['Google DV360', 'GoogleDV360', 'DV360', 'DV 360'],
    'DV360': ['Google DV360', 'GoogleDV360', 'DV360', 'DV 360'],
    'DSP': ['DSP', 'Amazon DSP'],
    'Teads': ['Teads'],
    'Spotify Ads': ['Spotify Ads', 'Spotify'],
    'Apple News': ['Apple News'],
    'Outbrain': ['Outbrain'],
    'MIQ': ['MIQ'],
    'CTV': ['CTV'],
    'Twitter（X）': ['Twitter', 'Twitter（X）', 'Twitter (X)'],
    'line': ['line', 'LINE'],
}

ALL_MEDIA_KEYWORDS = set()
for _k_list in MEDIA_KEYWORDS.values():
    ALL_MEDIA_KEYWORDS.update(_k_list)


@lru_cache(maxsize=256)
def _keyword_regex(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(str(keyword))
    # Avoid prefix collisions such as "TT" accidentally matching "TTD".
    if re.search(r'[A-Za-z0-9]', str(keyword)):
        # Keep numeric-adjacent forms (e.g. "TTD1500/月"), but block letter
        # prefix/suffix collisions (e.g. "TT" inside "TTD").
        return re.compile(rf'(?<![A-Za-z]){escaped}(?![A-Za-z])', re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _find_keyword_match(text: str, keyword: str, *, start: int = 0):
    if not text:
        return None
    return _keyword_regex(str(keyword)).search(text, pos=max(int(start or 0), 0))


def _contains_keyword(text: str, keyword: str) -> bool:
    return _find_keyword_match(text, keyword) is not None


def get_media_keywords(media: str) -> list[str]:
    """Return clause aliases for a spreadsheet media label."""
    text = str(media or '').strip()
    if text in MEDIA_KEYWORDS:
        return MEDIA_KEYWORDS[text]

    compact = text.casefold().replace(' ', '').replace('\u3000', '')
    for canonical, aliases in MEDIA_KEYWORDS.items():
        canonical_compact = canonical.casefold().replace(' ', '').replace('\u3000', '')
        if compact == canonical_compact:
            return aliases
        if any(compact == str(alias).casefold().replace(' ', '').replace('\u3000', '') for alias in aliases):
            return aliases

    return [text] if text else []


def _shared_trailing_percent(line: str) -> str | None:
    """Return a trailing shared percentage, such as ``+10%``."""
    percent_matches = list(re.finditer(r'(\d+(?:\.\d+)?)\s*%', line))
    if not percent_matches:
        return None

    media_ends: list[int] = []
    for aliases in MEDIA_KEYWORDS.values():
        for alias in aliases:
            media_match = _keyword_regex(alias).search(line)
            if media_match:
                media_ends.append(media_match.end())
    if not media_ends:
        return None

    last_percent = percent_matches[-1]
    if last_percent.start() <= max(media_ends):
        return None

    return f'+{last_percent.group(1)}%'


def _extract_media_segment(line, target_keywords):
    """
    Extract target-media segment from a multi-media clause line.
    """
    line = str(line or '')
    target_keywords = [str(kw) for kw in target_keywords if str(kw).strip()]
    target_kw_set = {kw.lower() for kw in target_keywords}

    target_pos = len(line)
    target_kw_end = target_pos
    for kw in target_keywords:
        match = _find_keyword_match(line, kw)
        if match and match.start() < target_pos:
            target_pos = match.start()
            target_kw_end = match.end()

    if target_pos >= len(line):
        return None

    next_media_pos = len(line)
    for kw_list in MEDIA_KEYWORDS.values():
        for kw in kw_list:
            if kw.lower() in target_kw_set:
                continue
            match = _find_keyword_match(line, kw, start=target_kw_end)
            if not match:
                continue
            idx = match.start()
            if idx >= next_media_pos:
                continue

            text_between = line[target_kw_end:idx]
            # strip common separators; if nothing remains, same grouped media list
            clean_text = re.sub(r'[\s\+\uFF0B\u3001\uFF0C,\u3002;\uFF1B\|&]', '', text_between)
            if not clean_text:
                continue
            # If no explicit numeric fee signal appears between keywords,
            # keep them in one grouped segment and use the trailing shared rate.
            if not re.search(r'\d|%', text_between):
                continue
            next_media_pos = idx

    segment = line[target_pos:next_media_pos].strip()
    segment = segment.rstrip('+\uFF0B').strip()
    if segment and '%' not in segment:
        shared_percent = _shared_trailing_percent(line)
        if shared_percent:
            segment = f'{segment}{shared_percent}'
    return segment if segment else None


# =============================================================================
# 时间感知条款提取
# =============================================================================

def extract_applicable_clause(clause: str, target_date_str: str) -> str:
    """Select the clause segment effective for the target billing month."""
    if not clause or not target_date_str:
        return clause

    target_match = re.search(r'(\d{4})\s*(?:\u5e74|-|/|\.)\s*(\d{1,2})', str(target_date_str))
    if not target_match:
        target_match = re.search(r'(\d{4})(\d{2})', str(target_date_str))
    if not target_match:
        return clause

    target_year = int(target_match.group(1))
    target_month = int(target_match.group(2))
    try:
        target_date = datetime(target_year, target_month, 1)
    except ValueError:
        return clause

    effective_words = r'(?:\u8d77|\u5f00\u59cb|\u540e|\u4ee5\u540e|\u4e4b\u540e)'
    marker_pattern = re.compile(
        r'(?:(20\d{2}|\d{2})\s*\u5e74\s*)?(\d{1,2})\s*\u6708(?:\u4efd)?\s*'
        + effective_words
        + r'|(?:(20\d{2}|\d{2})\s*[-/.]\s*(\d{1,2})\s*'
        + effective_words
        + r')'
    )
    range_pattern = re.compile(
        r'(?:(20\d{2}|\d{2})\s*\u5e74\s*)?(\d{1,2})\s*[-~\u81f3\u5230]\s*'
        r'(\d{1,2})\s*\u6708(?:\u4efd)?'
    )
    markers = []
    for marker in marker_pattern.finditer(clause):
        markers.append({
            'start': marker.start(),
            'end': marker.end(),
            'year': marker.group(1) or marker.group(3),
            'month': marker.group(2) or marker.group(4),
            'month_end': None,
            'kind': 'point',
        })
    for marker in range_pattern.finditer(clause):
        markers.append({
            'start': marker.start(),
            'end': marker.end(),
            'year': marker.group(1),
            'month': marker.group(2),
            'month_end': marker.group(3),
            'kind': 'range',
        })
    markers.sort(key=lambda marker: marker['start'])
    if not markers:
        return clause

    base_clause = clause[:markers[0]['start']].strip(' \t\r\n\uff0c,\uff1b;\u3002:')
    segments = []
    for index, marker in enumerate(markers):
        year_text = marker['year']
        month_text = marker['month']
        year = int(year_text) if year_text else target_year
        if year < 100:
            year += 2000
        try:
            segment_start_date = datetime(year, int(month_text), 1)
            segment_end_date = datetime(year, int(marker['month_end'] or month_text), 1)
        except ValueError:
            continue

        segment_start = marker['end']
        segment_end = markers[index + 1]['start'] if index + 1 < len(markers) else len(clause)
        segment_clause = clause[segment_start:segment_end].strip(' \t\r\n\uff0c,\uff1b;\u3002:')
        segments.append({
            'date': segment_start_date,
            'end_date': segment_end_date,
            'clause': segment_clause,
            'kind': marker['kind'],
        })

    applicable_segments = [
        segment
        for segment in segments
        if (
            segment['date'] <= target_date <= segment['end_date']
            if segment['kind'] == 'range'
            else segment['date'] <= target_date
        )
    ]
    if applicable_segments:
        applicable_segments.sort(key=lambda segment: segment['date'], reverse=True)
        return applicable_segments[0]['clause']

    return base_clause


# =============================================================================
# 阶梯费率解析
# =============================================================================

def _has_target_scoped_marker(
    clause: str,
    target_keywords: list[str],
    scope_markers: tuple[str, ...],
) -> bool:
    """Check whether a scope marker applies to the requested media."""
    lines = re.split(r'[;\n；。]', str(clause or ''))
    for line in lines:
        if not any(marker in line for marker in scope_markers):
            continue
        has_media = any(_contains_keyword(line, keyword) for keyword in ALL_MEDIA_KEYWORDS)
        has_target = any(_contains_keyword(line, keyword) for keyword in target_keywords)
        if not has_media or has_target:
            return True
    return False


def _generic_clause_scope_allowed(clause: str, target_keywords: list[str]) -> bool:
    """Allow generic rates only when no other media scope excludes the target."""
    has_any_media = any(_contains_keyword(clause, keyword) for keyword in ALL_MEDIA_KEYWORDS)
    has_target_media = any(_contains_keyword(clause, keyword) for keyword in target_keywords)
    return not has_any_media or has_target_media


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
    keywords = get_media_keywords(media)
    type_kw = '流水' if service_type == '流水' else '代投'
    check_consumption = combined_consumption if combined_consumption is not None else consumption

    # 规则2: 只有Google流水才有服务费
    if service_type == '流水' and media != 'Google':
        has_media_liushui = False
        for kw in keywords:
            escaped_kw = re.escape(str(kw))
            if re.search(
                rf'(?:{escaped_kw}[^\d%;\n]{{0,20}}流水|流水[^\d%;\n]{{0,20}}{escaped_kw})',
                clause,
                re.IGNORECASE,
            ):
                has_media_liushui = True
                break
        if not has_media_liushui:
            return (0.0, 0.0)

    if service_type != '流水' and _has_target_scoped_marker(
        clause,
        keywords,
        ('合计', '单渠道', '单个渠道', '全媒介', '客户端客户'),
    ):
        tier_result = parse_tiered_from_text(clause, check_consumption)
        if tier_result:
            return tier_result

    # 按行拆分
    lines = re.split(r'[;,\n；。，]', clause)
    lines = [l.strip() for l in lines if l.strip()]
    if len(lines) == 1:
        lines = [clause]

    # 先尝试精确匹配流水相关模式
    for line in lines:
        for kw in keywords:
            escaped_kw = re.escape(str(kw))
            flow_scope = rf'(?:{escaped_kw}[^\d%;\n]{{0,20}}流水|流水[^\d%;\n]{{0,20}}{escaped_kw})'
            zero_match = re.search(
                rf'{flow_scope}[^\d%;\n]*(?:服务费)?\s*0(?![\d.])',
                line,
                re.IGNORECASE,
            )
            if zero_match and service_type == '流水':
                return (0.0, 0.0)

            liushui_pct = re.search(
                rf'{flow_scope}[^\d%;\n]*(?:服务费)?\s*(\d+(?:\.\d+)?)\s*%',
                line,
                re.IGNORECASE,
            )
            if liushui_pct and service_type == '流水':
                return (float(liushui_pct.group(1)) / 100, 0.0)

            liushui_tier = re.search(
                rf'{flow_scope}[^\d%;\n]*(?:服务费)?\s*X',
                line,
                re.IGNORECASE,
            )
            if liushui_tier and service_type == '流水':
                result = parse_tiered_from_text(line, check_consumption)
                if result:
                    return result

    # 流水类型回退
    if service_type == '流水':
        has_target_flow_scope = _has_target_scoped_marker(clause, keywords, ('流水',))
        has_other_media = any(
            _contains_keyword(clause, kw)
            for kw in ALL_MEDIA_KEYWORDS
            if kw not in keywords
        )
        if not has_target_flow_scope and ('代投' in clause or has_other_media):
            return (0.0, 0.0)

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
            if not _has_target_scoped_marker(clause, keywords, ('流水',)):
                return (0.0, 0.0)
            if '代投' in clause and '流水' not in clause:
                return (0.0, 0.0)
            return (float(generic_pct.group(1)) / 100, 0.0)

        if re.fullmatch(r'0\.\d+', clause.strip()):
            if '代投' not in clause:
                return (float(clause.strip()), 0.0)

        return (0.0, 0.0)

    # 单渠道条款优先
    if _has_target_scoped_marker(clause, keywords, ('单个渠道', '单渠道')):
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
        contains_target = any(_contains_keyword(line, kw) for kw in keywords)

        contains_other = False
        if not contains_target:
            for kw in ALL_MEDIA_KEYWORDS:
                if kw in keywords:
                    continue
                if _contains_keyword(line, kw):
                    contains_other = True
                    break

        if contains_target:
            active_media_context = True
        elif contains_other:
            active_media_context = False

        if not active_media_context and not contains_target:
            has_any_media = any(_contains_keyword(clause, kw) for kw in ALL_MEDIA_KEYWORDS)
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
                _contains_keyword(line, kw)
                for kw in ALL_MEDIA_KEYWORDS
                if kw not in keywords
            )
            has_shared_scope = any(
                marker in line
                for marker in ('合计', '单渠道', '单个渠道', '全媒介', '客户端客户')
            )
            if _has_other_in_line and not has_shared_scope:
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
    if _has_target_scoped_marker(clause, keywords, ('单个渠道', '单渠道')):
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

    generic_scope_allowed = _generic_clause_scope_allowed(clause, keywords)

    if service_type == '代投' and generic_scope_allowed:
        daitou_pct = re.search(r'代投\s*(\d+(?:\.\d+)?)\s*%', clause)
        if daitou_pct:
            return (float(daitou_pct.group(1)) / 100, 0.0)

        daitou_fixed_pct = re.search(r'代投\s*(\d+)\s*[+＋]\s*(\d+(?:\.\d+)?)\s*%', clause)
        if daitou_fixed_pct:
            return (float(daitou_fixed_pct.group(2)) / 100, float(daitou_fixed_pct.group(1)))

    generic_consumption = re.search(r'消耗\s*(\d+(?:\.\d+)?)\s*%', clause)
    if generic_consumption and generic_scope_allowed:
        return (float(generic_consumption.group(1)) / 100, 0.0)

    generic_fee = re.search(r'服务费\s*(\d+(?:\.\d+)?)\s*%', clause)
    if generic_fee and generic_scope_allowed:
        return (float(generic_fee.group(1)) / 100, 0.0)

    if re.fullmatch(r'0\.\d+', clause.strip()):
        return (float(clause.strip()), 0.0)

    standalone_pct = re.fullmatch(r'(\d+(?:\.\d+)?)\s*%\s*[。.]?', clause.strip())
    if standalone_pct and generic_scope_allowed:
        return (float(standalone_pct.group(1)) / 100, 0.0)

    return (0.0, 0.0)
