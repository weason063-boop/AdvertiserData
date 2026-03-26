# -*- coding: utf-8 -*-
"""
测试database.py数据库操作函数
"""
import pytest
from database import (
    get_all_clients, get_client_by_name, upsert_client,
    upsert_billing_history, get_top_clients, get_billing_history,
    upsert_client_stats_batch
)
from api.services.dashboard_service import DashboardService


@pytest.mark.unit
class TestClientOperations:
    """测试客户CRUD操作"""
    
    def test_upsert_client_creates_new(self, test_db):
        """测试创建新客户"""
        # Arrange & Act
        client_id = upsert_client(
            name="测试客户",
            business_type="代投",
            department="技术部",
            entity="测试实体",
            fee_clause="Google代投8%"
        )
        
        # Assert
        assert client_id > 0
        client = get_client_by_name("测试客户")
        assert client is not None
        assert client['name'] == "测试客户"
        assert client['business_type'] == "代投"
    
    def test_upsert_client_updates_existing(self, test_db):
        """测试更新现有客户"""
        # Arrange - 先创建
        upsert_client(name="测试客户", fee_clause="Google代投8%")
        
        # Act - 更新
        new_id = upsert_client(name="测试客户", fee_clause="Google代投10%")
        
        # Assert
        client = get_client_by_name("测试客户")
        assert client['fee_clause'] == "Google代投10%"
    
    def test_get_all_clients_empty(self, test_db):
        """测试获取所有客户（空）"""
        clients = get_all_clients()
        assert clients == []
    
    def test_get_all_clients_with_data(self, test_db):
        """测试获取所有客户（有数据）"""
        # Arrange
        upsert_client(name="客户A")
        upsert_client(name="客户B")
        
        # Act
        clients = get_all_clients()
        
        # Assert
        assert len(clients) == 2
        names = [c['name'] for c in clients]
        assert "客户A" in names
        assert "客户B" in names
    
    def test_get_all_clients_with_search(self, test_db):
        """测试搜索客户"""
        # Arrange
        upsert_client(name="谷歌客户")
        upsert_client(name="TikTok客户")
        
        # Act
        results = get_all_clients(search="谷歌")
        
        # Assert
        assert len(results) == 1
        assert results[0]['name'] == "谷歌客户"


@pytest.mark.unit
class TestBillingOperations:
    """测试账单统计操作"""
    
    def test_upsert_billing_history(self, test_db):
        """测试更新账单历史"""
        # Act
        upsert_billing_history("2024-01", 100000, 8000)
        
        # Assert
        history = get_billing_history()
        assert len(history) == 1
        assert history[0]['month'] == "2024-01"
        assert history[0]['total_consumption'] == 100000
        assert history[0]['total_service_fee'] == 8000
    
    def test_upsert_billing_history_update(self, test_db):
        """测试更新已存在的账单历史"""
        # Arrange
        upsert_billing_history("2024-01", 100000, 8000)
        
        # Act - 更新同一月份
        upsert_billing_history("2024-01", 120000, 9600)
        
        # Assert
        history = get_billing_history()
        assert len(history) == 1  # 只有一条记录
        assert history[0]['total_consumption'] == 120000
    
    def test_get_billing_history_sorted(self, test_db):
        """测试获取账单历史按月份排序"""
        # Arrange
        upsert_billing_history("2024-03", 100000, 8000)
        upsert_billing_history("2024-01", 80000, 6400)
        upsert_billing_history("2024-02", 90000, 7200)
        
        # Act
        history = get_billing_history()
        
        # Assert
        assert len(history) == 3
        assert history[0]['month'] == "2024-01"
        assert history[1]['month'] == "2024-02"
        assert history[2]['month'] == "2024-03"


@pytest.mark.unit
class TestClientStats:
    """测试客户月度统计"""
    
    def test_upsert_client_stats_batch(self, test_db):
        """测试批量更新客户统计"""
        # Arrange
        stats = [
            {"name": "客户A", "consumption": 10000, "fee": 800},
            {"name": "客户B", "consumption": 5000, "fee": 400},
        ]
        
        # Act
        upsert_client_stats_batch("2024-01", stats)
        
        # Assert
        top_clients = get_top_clients("2024-01", limit=10)
        assert len(top_clients) == 2
    
    def test_get_top_clients(self, test_db):
        """测试获取TOP客户"""
        # Arrange
        stats = [
            {"name": "客户A", "consumption": 10000, "fee": 800},
            {"name": "客户B", "consumption": 20000, "fee": 1600},
            {"name": "客户C", "consumption": 5000, "fee": 400},
        ]
        upsert_client_stats_batch("2024-01", stats)
        
        # Act
        top_clients = get_top_clients("2024-01", limit=2)
        
        # Assert
        assert len(top_clients) == 2
        assert top_clients[0]['client_name'] == "客户B"  # 最高消耗
        assert top_clients[1]['client_name'] == "客户A"
    
    def test_get_client_trend_empty(self, test_db):
        """测试获取客户趋势（无数据）"""
        # Act
        result = DashboardService().get_client_trend("不存在的客户")
        
        # Assert
        assert result['client_name'] == "不存在的客户"
        assert result['data'] == []
        assert result['summary']['total_consumption'] == 0
    
    def test_get_client_trend_with_data(self, test_db):
        """测试获取客户趋势（有数据）"""
        # Arrange
        stats = [{"name": "测试客户", "consumption": 10000, "fee": 800}]
        upsert_client_stats_batch("2024-01", stats)
        upsert_client_stats_batch("2024-02", [{"name": "测试客户", "consumption": 12000, "fee": 960}])
        
        # Act
        result = DashboardService().get_client_trend("测试客户")
        
        # Assert
        assert result['client_name'] == "测试客户"
        assert len(result['data']) == 12  # 填充12个月
        assert result['summary']['total_consumption'] == 22000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
