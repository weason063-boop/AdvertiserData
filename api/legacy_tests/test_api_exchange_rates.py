# -*- coding: utf-8 -*-
"""
测试汇率API端点
"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app


client = TestClient(app)


@pytest.mark.api
class TestExchangeRatesAPI:
    """测试汇率API"""
    
    def test_get_cfets_rates_success(self):
        """测试获取CFETS汇率（成功）"""
        # Act
        with patch('api.services.exchange_rate_service.fetch_cfets_rates') as mock_fetch:
            # Mock返回数据
            mock_fetch.return_value = {
                "CNY/USD": 7.2345,
                "date": "2024-02-07",
                "source": "CFETS"
            }
            
            response = client.get("/api/exchange-rates/cfets")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "CNY/USD" in data
            assert data["source"] == "CFETS"
    
    def test_get_hangseng_rates_success(self):
        """测试获取恒生汇率（成功）"""
        # Act
        with patch('api.services.exchange_rate_service.fetch_hangseng_rates') as mock_fetch:
            # Mock返回数据
            mock_fetch.return_value = {
                "USD/HKD": 7.8234,
                "EUR/HKD": 8.5123,
                "date": "2024-02-07",
                "source": "Hang Seng"
            }
            
            response = client.get("/api/exchange-rates/hangseng")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "USD/HKD" in data
            assert data["source"] == "Hang Seng"
    
    def test_get_pbc_rates_success(self):
        """测试获取央行汇率（成功）"""
        # Act
        with patch('api.services.exchange_rate_service.fetch_pbc_rates') as mock_fetch:
            # Mock返回数据
            mock_fetch.return_value = {
                "USD/CNY": 7.2000,
                "EUR/CNY": 7.8500,
                "date": "2024-02-07",
                "source": "PBC"
            }
            
            response = client.get("/api/exchange-rates/pbc")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert "USD/CNY" in data
            assert data["source"] == "PBC"
    
    def test_get_all_rates_success(self):
        """测试获取所有汇率（成功）"""
        # Act
        with patch('api.services.exchange_rate_service.fetch_cfets_rates') as mock_cfets, \
             patch('api.services.exchange_rate_service.fetch_hangseng_rates') as mock_hs, \
             patch('api.services.exchange_rate_service.fetch_pbc_rates') as mock_pbc:
            
            # Mock返回数据
            mock_cfets.return_value = {"CNY/USD": 7.2345, "source": "CFETS"}
            mock_hs.return_value = {"USD/HKD": 7.8234, "source": "Hang Seng"}
            mock_pbc.return_value = {"USD/CNY": 7.2000, "source": "PBC"}
            
            response = client.get("/api/exchange-rates/all")
            
            # Assert
            assert response.status_code == 200
            data = response.json()
            assert 'cfets' in data
            assert 'hangseng' in data
            assert 'pbc' in data
    
    @pytest.mark.slow
    def test_get_cfets_rates_network_error(self):
        """测试CFETS汇率网络错误处理"""
        # Act
        with patch('api.services.exchange_rate_service.fetch_cfets_rates') as mock_fetch:
            # Mock网络错误
            mock_fetch.side_effect = Exception("Network error")
            
            response = client.get("/api/exchange-rates/cfets")
            
            # Assert - 应该返回错误或默认值
            assert response.status_code in [200, 500, 503]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
