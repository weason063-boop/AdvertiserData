# -*- coding: utf-8 -*-
"""
测试Dashboard API端点
"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import upsert_billing_history, upsert_client_stats_batch


client = TestClient(app)


@pytest.mark.api
class TestDashboardAPI:
    """测试Dashboard API"""
    
    def test_get_dashboard_stats_empty(self, test_db):
        """测试获取Dashboard统计（空数据）"""
        # Act
        response = client.get("/api/dashboard/stats")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert 'history' in data
        assert 'top_clients' in data
        assert isinstance(data['history'], list)
        assert isinstance(data['top_clients'], list)
    
    def test_get_dashboard_stats_with_data(self, test_db):
        """测试获取Dashboard统计（有数据）"""
        # Arrange - 添加历史数据
        upsert_billing_history("2024-01", 100000, 8000)
        upsert_billing_history("2024-02", 120000, 9600)
        
        # Arrange - 添加客户统计
        stats = [
            {"name": "客户A", "consumption": 50000, "fee": 4000},
            {"name": "客户B", "consumption": 30000, "fee": 2400},
        ]
        upsert_client_stats_batch("2024-02", stats)
        
        # Act
        response = client.get("/api/dashboard/stats")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data['history']) == 2
        assert len(data['top_clients']) == 2
        assert data['top_clients'][0]['client_name'] == "客户A"  # 按消耗排序
    
    def test_get_top_clients_latest_month(self, test_db):
        """测试获取最新月份TOP客户"""
        # Arrange
        stats = [
            {"name": "客户A", "consumption": 50000, "fee": 4000},
            {"name": "客户B", "consumption": 30000, "fee": 2400},
            {"name": "客户C", "consumption": 20000, "fee": 1600},
        ]
        upsert_client_stats_batch("2024-02", stats)
        
        # Act
        response = client.get("/api/dashboard/top-clients")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3
        assert data[0]['client_name'] == "客户A"
    
    def test_get_month_top_clients(self, test_db):
        """测试获取指定月份TOP10客户"""
        # Arrange
        stats_jan = [
            {"name": "客户A", "consumption": 50000, "fee": 4000},
            {"name": "客户B", "consumption": 30000, "fee": 2400},
        ]
        stats_feb = [
            {"name": "客户C", "consumption": 60000, "fee": 4800},
            {"name": "客户D", "consumption": 40000, "fee": 3200},
        ]
        upsert_client_stats_batch("2024-01", stats_jan)
        upsert_client_stats_batch("2024-02", stats_feb)
        
        # Act
        response = client.get("/api/dashboard/month/2024-01/top-clients")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['month'] == "2024-01"
        assert len(data['clients']) == 2
        assert data['clients'][0]['client_name'] == "客户A"
    
    def test_get_client_trend(self, test_db):
        """测试获取客户趋势"""
        # Arrange
        upsert_client_stats_batch("2024-01", [{"name": "测试客户", "consumption": 10000, "fee": 800}])
        upsert_client_stats_batch("2024-02", [{"name": "测试客户", "consumption": 12000, "fee": 960}])
        
        # Act
        response = client.get("/api/dashboard/client/测试客户/trend")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['client_name'] == "测试客户"
        assert 'data' in data
        assert 'summary' in data
        assert len(data['data']) == 12  # 12个月数据


@pytest.mark.api
class TestDashboardInsights:
    """测试Dashboard洞察API"""
    
    def test_get_insights_empty(self, test_db):
        """测试获取洞察（空数据）"""
        # Act
        response = client.get("/api/dashboard/insights")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        # 空数据应返回空结构
        assert isinstance(data, dict)
    
    def test_get_insights_with_data(self, test_db):
        """测试获取洞察（有数据）"""
        # Arrange - 创建多个月的数据模拟趋势
        for month, clients_data in [
            ("2024-01", [
                {"name": "客户A", "consumption": 100000, "fee": 8000},
                {"name": "客户B", "consumption": 50000, "fee": 4000},
            ]),
            ("2024-02", [
                {"name": "客户A", "consumption": 200000, "fee": 16000},  # 增长客户
                {"name": "客户B", "consumption": 25000, "fee": 2000},   # 下降客户
            ]),
        ]:
            upsert_client_stats_batch(month, clients_data)
        
        # Act
        response = client.get("/api/dashboard/insights")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert 'metrics' in data or 'segmentation' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
