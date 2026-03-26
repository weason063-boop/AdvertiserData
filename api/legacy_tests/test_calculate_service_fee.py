# -*- coding: utf-8 -*-
"""
测试calculate_service_fee.py中的核心费用计算逻辑
"""
import pytest
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from calculate_service_fee import parse_fee_clause


class TestParseFeeClause:
    """测试parse_fee_clause函数"""
    
    @pytest.mark.unit
    def test_basic_percentage_rate(self):
        """测试基础百分比费率"""
        # Arrange
        clause = "Google代投8%"
        media = "Google"
        service_type = "代投"
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type)
        
        # Assert
        assert rate == 0.08
        assert fixed == 0.0
    
    @pytest.mark.unit
    def test_percentage_with_fixed_fee(self):
        """测试百分比 + 固定费用"""
        # Arrange
        clause = "Google代投8% + 500元"
        media = "Google"
        service_type = "代投"
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type)
        
        # Assert
        assert rate == 0.08
        assert fixed == 500.0
    
    @pytest.mark.unit
    def test_fixed_fee_only(self):
        """测试仅固定费用"""
        # Arrange  
        clause = "固定500元"
        media = "Google"
        service_type = "代投"
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type)
        
        # Assert
        assert rate == 0.0
        assert fixed == 500.0
    
    @pytest.mark.unit
    def test_tiered_rate_low_consumption(self):
        """测试阶梯费率 - 低消耗"""
        # Arrange
        clause = "Google代投: 0-10万8%, 10-20万6%, 20万以上4%"
        media = "Google"
        service_type = "代投"
        consumption = 50000  # 5万，应该是8%
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type, consumption)
        
        # Assert
        assert rate == 0.08
    
    @pytest.mark.unit
    def test_tiered_rate_high_consumption(self):
        """测试阶梯费率 - 高消耗"""
        # Arrange
        clause = "Google代投: 0-10万8%, 10-20万6%, 20万以上4%"
        media = "Google"
        service_type = "代投"
        consumption = 250000  # 25万，应该是4%
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type, consumption)
        
        # Assert
        assert rate == 0.04
    
    @pytest.mark.unit
    def test_no_fee_clause(self):
        """测试无条款"""
        # Arrange & Act
        rate1, fixed1 = parse_fee_clause(None, "Google", "代投")
        rate2, fixed2 = parse_fee_clause("无", "Google", "代投")
        rate3, fixed3 = parse_fee_clause("0", "Google", "代投")
        
        # Assert
        assert rate1 == 0.0 and fixed1 == 0.0
        assert rate2 == 0.0 and fixed2 == 0.0
        assert rate3 == 0.0 and fixed3 == 0.0
    
    @pytest.mark.unit
    def test_non_google_liushui_default_zero(self):
        """测试非Google媒介的流水类型默认为0"""
        # Arrange
        clause = "TikTok代投8%"  # 没有明确说TikTok流水
        media = "TikTok"
        service_type = "流水"
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type)
        
        # Assert
        assert rate == 0.0
        assert fixed == 0.0
    
    @pytest.mark.unit
    def test_google_liushui_has_fee(self):
        """测试Google流水有费用"""
        # Arrange
        clause = "Google流水5%"
        media = "Google"
        service_type = "流水"
        
        # Act
        rate, fixed = parse_fee_clause(clause, media, service_type)
        
        # Assert
        assert rate == 0.05
    
    @pytest.mark.unit
    def test_multiple_media_clauses(self):
        """测试多媒介条款"""
        # Arrange
        clause = """
        Google代投8%
        TikTok代投10%
        Facebook代投7%
        """
        
        # Act - 测试Google
        rate_google, _ = parse_fee_clause(clause, "Google", "代投")
        # Act - 测试TikTok
        rate_tiktok, _ = parse_fee_clause(clause, "TikTok", "代投")
        # Act - 测试Facebook
        rate_fb, _ = parse_fee_clause(clause, "Facebook", "代投")
        
        # Assert
        assert rate_google == 0.08
        assert rate_tiktok == 0.10
        assert rate_fb == 0.07
    
    @pytest.mark.unit
    @pytest.mark.parametrize("media,expected_rate", [
        ("Google", 0.08),
        ("TikTok", 0.08),
        ("Facebook", 0.08),
        ("Meta", 0.08),
    ])
    def test_various_media_types(self, media, expected_rate):
        """参数化测试不同媒介类型"""
        clause = f"{media}代投8%"
        rate, _ = parse_fee_clause(clause, media, "代投")
        assert rate == expected_rate
    
    @pytest.mark.unit
    def test_edge_case_empty_string(self):
        """边界case empty string"""
        rate, fixed = parse_fee_clause("", "Google", "代投")
        assert rate == 0.0
        assert fixed == 0.0
    
    @pytest.mark.unit
    def test_complex_tiered_with_combined_consumption(self):
        """测试复杂阶梯费率（GG+Bing合计）"""
        # Arrange
        clause = "GG+Bing合计: 0-10万8%, 10-20万6%, 20万以上4%"
        media = "Google"
        service_type = "代投"
        consumption = 80000  # Google单独8万
        combined_consumption = 150000  # GG+Bing合计15万，应该用6%
        
        # Act
        rate, fixed = parse_fee_clause(
            clause, media, service_type, 
            consumption, combined_consumption
        )
        
        # Assert
        assert rate == 0.06  # 使用合计消耗判断阶梯


class TestCalculateServiceFeeEdgeCases:
    """测试边界条件和异常情况"""
    
    @pytest.mark.unit
    def test_very_high_consumption(self):
        """测试超高消耗"""
        clause = "Google代投8%"
        rate, _ = parse_fee_clause(clause, "Google", "代投", consumption=10000000)  # 1000万
        assert rate == 0.08
    
    @pytest.mark.unit
    def test_zero_consumption(self):
        """测试零消耗"""
        clause = "Google代投8%"
        rate, _ = parse_fee_clause(clause, "Google", "代投", consumption=0)
        assert rate == 0.08  # 费率不变
    
    @pytest.mark.unit
    def test_negative_consumption_should_still_work(self):
        """测试负数消耗（虽然不应该发生）"""
        clause = "Google代投8%"
        rate, _ = parse_fee_clause(clause, "Google", "代投", consumption=-1000)
        assert rate == 0.08  # 应该仍然返回费率
    
    @pytest.mark.unit
    def test_special_characters_in_clause(self):
        """测试条款中包含特殊字符"""
        clause = "Google代投8%（含税）"
        rate, _ = parse_fee_clause(clause, "Google", "代投")
        assert rate == 0.08
    
    @pytest.mark.unit
    def test_case_insensitive_media_keywords(self):
        """测试媒介关键词大小写不敏感"""
        clause = "google代投8%"  # 小写
        rate, _ = parse_fee_clause(clause, "Google", "代投")
        assert rate == 0.08


@pytest.mark.integration
class TestEndToEndCalculation:
    """端到端集成测试（需要完整的计算流程）"""
    
    def test_full_calculation_workflow(self, tmp_path):
        """测试完整的计算工作流程"""
        # 这个测试需要Excel文件和完整的calculate_service_fee函数
        # 暂时跳过，等待后续实现
        pytest.skip("需要完整的Excel文件和main计算函数")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
