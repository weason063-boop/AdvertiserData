# -*- coding: utf-8 -*-
"""
pytest fixtures and test configuration
"""
import pytest
import sqlite3
import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import init_db, get_connection
from main import app


@pytest.fixture(scope="function")
def test_db():
    """
    创建临时测试数据库
    
    Yields:
        Path: 测试数据库路径
    """
    # 使用临时数据库
    test_db_path = Path(__file__).parent / "test_contracts.db"
    
    # 临时修改环境变量
    original_db_path = os.environ.get('DB_PATH')
    os.environ['DB_PATH'] = str(test_db_path)
    
    # 重新导入database模块使其使用新路径
    import database
    database.DB_PATH = test_db_path
    
    # 初始化测试数据库
    init_db()
    
    yield test_db_path
    
    # 清理
    if test_db_path.exists():
        test_db_path.unlink()
    
    # 恢复环境变量
    if original_db_path:
        os.environ['DB_PATH'] = original_db_path
    else:
        os.environ.pop('DB_PATH', None)


@pytest.fixture(scope="function")
def db_connection(test_db):
    """
    返回数据库连接
    
    Args:
        test_db: 测试数据库路径fixture
        
    Yields:
        sqlite3.Connection: 数据库连接
    """
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def client():
    """
    FastAPI测试客户端
    
    Returns:
        TestClient: FastAPI测试客户端
    """
    return TestClient(app)


@pytest.fixture
def sample_client_data():
    """
    示例客户数据
    
    Returns:
        dict: 客户数据字典
    """
    return {
        "name": "测试客户",
        "business_type": "代投",
        "department": "技术部",
        "entity": "测试实体",
        "fee_clause": "Google代投8%"
    }


@pytest.fixture
def sample_consumption_data():
    """
    示例消耗数据
    
    Returns:
        dict: 消耗数据
    """
    return {
        "客户": "测试客户",
        "媒介": "Google",
        "服务类型": "代投",
        "消耗": 10000.0
    }


@pytest.fixture
def mock_excel_file(tmp_path):
    """
    创建临时Excel文件用于测试
    
    Args:
        tmp_path: pytest临时目录fixture
        
    Returns:
        Path: Excel文件路径
    """
    import pandas as pd
    
    excel_path = tmp_path / "test_data.xlsx"
    df = pd.DataFrame({
        "客户": ["测试客户1", "测试客户2"],
        "媒介": ["Google", "TikTok"],
        "服务类型": ["代投", "流水"],
        "消耗": [10000.0, 5000.0]
    })
    df.to_excel(excel_path, index=False)
    
    return excel_path
