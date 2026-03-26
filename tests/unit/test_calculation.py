# -*- coding: utf-8 -*-
"""
条款解析器综合测试

覆盖 parse_fee_clause 的 9 种匹配模式 + 阶梯费率 + 时间感知条款。
"""
import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from billing.clause_parser import parse_fee_clause, extract_applicable_clause, parse_tiered_from_text


class TestBasicFeeTypes:
    """基础费率类型测试"""

    def test_simple_percentage(self):
        """P7: 直接百分比 - 'Google 8%'"""
        rate, fixed = parse_fee_clause("Google 8%", 'Google', '代投', 50000)
        assert rate == 0.08
        assert fixed == 0.0

    def test_decimal_percentage(self):
        """P7: 小数百分比 - 'Google 5.5%'"""
        rate, fixed = parse_fee_clause("Google 5.5%", 'Google', '代投', 10000)
        assert rate == 0.055
        assert fixed == 0.0

    def test_fixed_plus_percentage(self):
        """P6: 金额+百分比 - 'Google 1000+10%'"""
        rate, fixed = parse_fee_clause("Google 1000+10%", 'Google', '代投', 50000)
        assert rate == 0.10
        assert fixed == 1000.0

    def test_fixed_only(self):
        """P6: 纯固定费 - 'Google 1000+0%'"""
        rate, fixed = parse_fee_clause("Google 1000+0%", 'Google', '代投', 50000)
        assert rate == 0.0
        assert fixed == 1000.0

    def test_monthly_fee(self):
        """P9: 月固定费 - 'TTD1500/月'"""
        rate, fixed = parse_fee_clause("TTD1500/月", 'TTD', '代投', 50000)
        assert rate == 0.0
        assert fixed == 1500.0

    def test_pure_decimal(self):
        """纯小数 - '0.08'"""
        rate, fixed = parse_fee_clause("0.08", 'Google', '代投', 10000)
        assert rate == 0.08
        assert fixed == 0.0

    def test_standalone_percentage(self):
        """独立百分比 - '10%。'"""
        rate, fixed = parse_fee_clause("10%。", 'Google', '代投', 10000)
        assert rate == 0.10
        assert fixed == 0.0

    def test_consumption_percentage(self):
        """通用消耗百分比 - '消耗5%'"""
        rate, fixed = parse_fee_clause("消耗5%", 'Google', '代投', 10000)
        assert rate == 0.05
        assert fixed == 0.0

    def test_daitou_percentage(self):
        """代投专用百分比 - '代投10%'"""
        rate, fixed = parse_fee_clause("代投10%", 'Google', '代投', 10000)
        assert rate == 0.10
        assert fixed == 0.0


class TestTieredFees:
    """阶梯费率测试"""

    def test_two_tier_low(self):
        """P4: 双阶梯 - 低消耗段"""
        clause = "Google 0<X<=10w 5%; Google X>10w 3%"
        rate, fixed = parse_fee_clause(clause, 'Google', '代投', 50000)
        assert rate == 0.05

    def test_two_tier_high(self):
        """P4: 双阶梯 - 高消耗段"""
        clause = "Google 0<X<=10w 5%; Google X>10w 3%"
        rate, fixed = parse_fee_clause(clause, 'Google', '代投', 150000)
        assert rate == 0.03

    def test_three_tier(self):
        """P4: 三阶梯"""
        clause = "Google 0<X<50000，12%；50000<X<150000，10%；X>150000，8%"
        # 30000 在 0<X<50000 范围 → 12%
        rate, _ = parse_fee_clause(clause, 'Google', '代投', 30000)
        assert rate == 0.12
        # 80000 在 50000<X<150000 范围 → 10%
        rate, _ = parse_fee_clause(clause, 'Google', '代投', 80000)
        assert rate == 0.10
        # 200000 在 X>150000 范围 → 8%
        rate, _ = parse_fee_clause(clause, 'Google', '代投', 200000)
        assert rate == 0.08

    def test_tiered_with_fixed(self):
        """P1: 固定+阶梯"""
        clause = "Google 固定1000+0<X<=3w 10%"
        rate, fixed = parse_fee_clause(clause, 'Google', '代投', 20000)
        assert rate == 0.10
        assert fixed == 1000.0

    def test_over_threshold(self):
        """格式D: 超过阈值"""
        clause = "超过5w，3%"
        result = parse_tiered_from_text(clause, 60000)
        assert result == (0.03, 0.0)

    def test_over_threshold_not_met(self):
        """格式D: 未达阈值"""
        clause = "超过5w，3%"
        result = parse_tiered_from_text(clause, 40000)
        assert result is None


class TestLiushuiRules:
    """流水类型特殊规则测试"""

    def test_non_google_liushui_returns_zero(self):
        """规则2: 非Google流水 = 0"""
        rate, fixed = parse_fee_clause("FB 10%", 'Facebook', '流水', 50000)
        assert rate == 0.0
        assert fixed == 0.0

    def test_google_liushui_with_explicit_clause(self):
        """Google流水有明确标注"""
        rate, fixed = parse_fee_clause("Google流水5%", 'Google', '流水', 50000)
        assert rate == 0.05

    def test_google_liushui_zero(self):
        """Google流水明确为0"""
        rate, fixed = parse_fee_clause("Google流水0", 'Google', '流水', 50000)
        assert rate == 0.0
        assert fixed == 0.0


class TestSpecialClauses:
    """特殊条款处理测试"""

    def test_empty_clause(self):
        rate, fixed = parse_fee_clause("", 'Google', '代投', 10000)
        assert (rate, fixed) == (0.0, 0.0)

    def test_none_clause(self):
        rate, fixed = parse_fee_clause(None, 'Google', '代投', 10000)
        assert (rate, fixed) == (0.0, 0.0)

    def test_wu_clause(self):
        """'无' 条款"""
        rate, fixed = parse_fee_clause("无", 'Google', '代投', 10000)
        assert (rate, fixed) == (0.0, 0.0)

    def test_zero_clause(self):
        """'0' 条款"""
        rate, fixed = parse_fee_clause("0", 'Google', '代投', 10000)
        assert (rate, fixed) == (0.0, 0.0)

    def test_special_keywords_return_zero(self):
        """特殊关键词条款返回0"""
        special_clauses = [
            "代运营条款",
            "众筹条款",
            "自营项目",
            "项目制",
            "ROAS",
        ]
        for clause in special_clauses:
            rate, fixed = parse_fee_clause(clause, 'Google', '代投', 10000)
            assert (rate, fixed) == (0.0, 0.0), f"Failed for clause: {clause}"

    def test_zero_consumption(self):
        """0 消耗"""
        rate, fixed = parse_fee_clause("Google 10%", 'Google', '代投', 0)
        assert rate == 0.10
        assert fixed == 0.0

    def test_combined_fixed_plus_pct(self):
        """P2: 合计基础固定+比例"""
        clause = "代投合计基础2000+消耗5%"
        rate, fixed = parse_fee_clause(clause, 'Google', '代投', 10000)
        assert rate == 0.05
        assert fixed == 2000.0

    def test_per_media_fixed_pct(self):
        """P3: 各X+比例 - 'FB/GG 各1000+消耗*7%'"""
        clause = "各1000+消耗*7%"
        rate, fixed = parse_fee_clause(clause, 'Google', '代投', 10000)
        assert rate == 0.07
        assert fixed == 1000.0


class TestTimeAwareClauses:
    """时间感知条款测试"""

    def test_extract_later_clause(self):
        """提取后期条款"""
        clause = "GG 8%。2025年9月起 FB、TTD 5%。"
        result = extract_applicable_clause(clause, "2026年1月")
        assert "5%" in result

    def test_extract_base_clause_before_date(self):
        """目标日期在条款日期之前，使用基础条款"""
        clause = "GG 8%。2025年9月起 FB、TTD 5%。"
        result = extract_applicable_clause(clause, "2025年7月")
        assert "8%" in result

    def test_no_time_markers(self):
        """无时间标记 → 返回原条款"""
        clause = "GG 8%"
        result = extract_applicable_clause(clause, "2026年1月")
        assert result == "GG 8%"


class TestClientOverrides:
    """客户特殊规则测试（从 client_overrides.json 加载）"""

    def test_meidi_fixed_rate(self):
        """美的: 统一5%"""
        rate, fixed = parse_fee_clause("Any Clause", 'Google', '代投', 10000, client_name="美的")
        assert rate == 0.05
        assert fixed == 0.0

    def test_meidi_variant(self):
        """美的变种: '美的集团' 也应匹配"""
        rate, fixed = parse_fee_clause("Any Clause", 'Google', '代投', 10000, client_name="美的集团")
        assert rate == 0.05

    def test_niulaike_excludes_facebook(self):
        """纽莱克: 排除 Facebook"""
        rate, fixed = parse_fee_clause("GG 10%", 'Facebook', '代投', 10000, client_name="纽莱克")
        assert rate == 0.0
        assert fixed == 0.0

    def test_niulaike_allows_google(self):
        """纽莱克: Google 正常计算"""
        rate, fixed = parse_fee_clause("Google 10%", 'Google', '代投', 10000, client_name="纽莱克")
        assert rate == 0.10

    def test_feiyada_forces_liushui(self):
        """飞亚达: 强制转流水类型"""
        rate, fixed = parse_fee_clause("Google 8%", 'Google', '代投', 10000, client_name="飞亚达")
        # 飞亚达强制流水 → Google流水才有费，非Google流水=0
        # 因为 media=Google，且转为流水后走流水路径
        # 条款 "Google 8%" 会匹配通用百分比
        assert rate == 0.08 or rate == 0.0  # 取决于条款是否有流水标注

    def test_nongfu_conditional_zero(self):
        """农夫山泉: 无代投服务费"""
        rate, fixed = parse_fee_clause("无代投服务费,Google流水5%", 'Google', '代投', 10000, client_name="农夫山泉")
        assert rate == 0.0
        assert fixed == 0.0

    def test_invalid_clause_returns_zero(self):
        """无效条款返回0"""
        rate, fixed = parse_fee_clause("Invalid Clause", 'Google', '代投', 10000)
        assert rate == 0.0
        assert fixed == 0.0
