# -*- coding: utf-8 -*-
"""
添加时间感知功能到parse_fee_clause
"""
import re
from datetime import datetime

def extract_applicable_clause(clause, target_date_str):
    """
    从包含多个时间段的条款中提取适用于目标日期的子条款
    
    Args:
        clause: 完整的费率条款
        target_date_str: 目标日期，格式如 "2026年1月"
        
    Returns:
        适用的子条款字符串
    """
    # 解析目标日期
    # 支持格式: "2026年1月", "2026-01", "202601"
    year_month_match = re.search(r'(\d{4})[年\-](\d{1,2})', target_date_str)
    if not year_month_match:
        return clause  # 无法解析日期，返回原条款
    
    target_year = int(year_month_match.group(1))
    target_month = int(year_month_match.group(2))
    target_date = datetime(target_year, target_month, 1)
    
    # 提取所有时间标记及其对应的条款
    # 模式: "YYYY年M月起" 或 "YY年M月起" 或 "M月起"
    time_pattern = r'((?:20)?\d{2,4}年)?(\d{1,2})月起'
    
    # 分割条款为时间段
    segments = []
    parts = re.split(time_pattern, clause)
    
    # parts会是: [前缀, 年份1, 月份1, 条款1, 年份2, 月份2, 条款2, ...]
    # 提取时间标记和对应的条款
    i = 0
    base_clause = ""
    
    # 第一部分是默认条款（没有时间标记的）
    if parts and parts[0]:
        base_clause = parts[0].strip()
    
    i = 1
    while i < len(parts):
        if i + 2 < len(parts):
            year_str = parts[i]  # 可能是None
            month_str = parts[i + 1]
            seg_clause = parts[i + 2]
            
            # 解析年份
            if year_str:
                # 去掉"年"字
                year_str = year_str.replace('年', '').strip()
                if len(year_str) == 2:  # 简写年份如"25年"
                    year = 2000 + int(year_str)
                else:
                    year = int(year_str)
            else:
                # 没有年份，默认使用目标年份或当前年份
                year = target_year
            
            month = int(month_str)
            
            # 创建该时间段的起始日期
            seg_date = datetime(year, month, 1)
            
            # 找到下一个时间标记的位置（作为结束日期）
            # 提取该段的纯条款内容（去掉下一个时间标记）
            next_time_match = re.search(time_pattern, seg_clause)
            if next_time_match:
                # 只取到下一个时间标记之前的内容
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
    
    # 选择适用的条款
    # 找到所有<=目标日期的时间段，取最新的一个
    applicable_segments = [s for s in segments if s['date'] <= target_date]
    
    if applicable_segments:
        # 按日期排序，取最新的
        applicable_segments.sort(key=lambda x: x['date'], reverse=True)
        return applicable_segments[0]['clause']
    else:
        # 没有找到适用的时间段，使用基础条款
        return base_clause


# 测试
test_cases = [
    {
        'clause': '【GG、FB合计 2000+消耗*10%；2024年9月起 合计 2000+消耗*5%；2025年10月起 GG 1000+消耗5%，FB流水0%】（钉钉）bing，10%。',
        'date': '2026年1月',
        'expected': 'GG 1000+消耗5%，FB流水0%'
    },
    {
        'clause': 'FB/GG 各1000+10%。GG流水服务费2%。2025年12月起 FB/GG 各1000+消耗*7%',
        'date': '2026年1月',
        'expected': 'FB/GG 各1000+消耗*7%'
    },
    {
        'clause': 'FB/GG 各1000+10%。GG流水服务费2%。2025年12月起 FB/GG 各1000+消耗*7%',
        'date': '2025年11月',
        'expected': 'FB/GG 各1000+10%'
    }
]

print("=" * 80)
print("时间感知条款解析测试")
print("=" * 80)

for i, test in enumerate(test_cases, 1):
    result = extract_applicable_clause(test['clause'], test['date'])
    print(f"\n测试{i}:")
    print(f"  日期: {test['date']}")
    print(f"  原条款: {test['clause'][:60]}...")
    print(f"  提取结果: {result}")
    print(f"  预期结果: {test['expected']}")
    print(f"  ✅ 通过" if test['expected'] in result else f"  ❌ 失败")

print("\n" + "=" * 80)
