# -*- coding: utf-8 -*-
"""
测试客户管理API端点
"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import upsert_client


client = TestClient(app)


@pytest.mark.api
class TestClientsAPI:
    """测试客户管理API"""
    
    def test_get_all_clients_empty(self, test_db):
        """测试获取所有客户（空数据）"""
        # Act
        response = client.get("/api/clients")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_get_all_clients_with_data(self, test_db):
        """测试获取所有客户（有数据）"""
        # Arrange
        upsert_client(name="测试客户A", business_type="代投")
        upsert_client(name="测试客户B", business_type="流水")
        
        # Act
        response = client.get("/api/clients")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [c['name'] for c in data]
        assert "测试客户A" in names
        assert "测试客户B" in names
    
    def test_search_clients(self, test_db):
        """测试搜索客户"""
        # Arrange
        upsert_client(name="Google客户")
        upsert_client(name="TikTok客户")
        upsert_client(name="Facebook客户")
        
        # Act
        response = client.get("/api/clients?search=Google")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['name'] == "Google客户"
    
    def test_get_client_by_name_success(self, test_db):
        """测试根据名称获取客户（成功）"""
        # Arrange
        upsert_client(
            name="测试客户",
            business_type="代投",
            department="技术部",
            fee_clause="Google代投8%"
        )
        
        # Act
        response = client.get("/api/clients/测试客户")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['name'] == "测试客户"
        assert data['business_type'] == "代投"
        assert data['fee_clause'] == "Google代投8%"
    
    def test_get_client_by_name_not_found(self, test_db):
        """测试根据名称获取客户（不存在）"""
        # Act
        response = client.get("/api/clients/不存在的客户")
        
        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()['detail'].lower()
    
    def test_update_client_success(self, test_db):
        """测试更新客户（成功）"""
        # Arrange
        upsert_client(name="测试客户", fee_clause="Google代投8%")
        
        # Act
        response = client.put(
            "/api/clients/测试客户",
            json={"fee_clause": "Google代投10%"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        
        # Verify update
        verify = client.get("/api/clients/测试客户")
        assert verify.json()['fee_clause'] == "Google代投10%"
    
    def test_update_client_not_found(self, test_db):
        """测试更新客户（不存在）"""
        # Act
        response = client.put(
            "/api/clients/不存在的客户",
            json={"fee_clause": "Google代投10%"}
        )
        
        # Assert
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
