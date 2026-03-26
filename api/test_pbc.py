import requests
from bs4 import BeautifulSoup
import sys

def test_pbc():
    url = "https://www.pbc.gov.cn/rmyh/108976/109428/index.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.pbc.gov.cn/"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        print(f"Status Code: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 尝试查找主要的表格或列表
        # 寻找包含 "2026" 或 "美元" 的文本
        items = soup.find_all(text=lambda t: t and ("美元" in t or "2026" in t))
        for item in items[:10]:
            print(f"Found match: {item.strip()}")
            
        # 打印部分 HTML 以供分析
        print("\n--- HTML Extract ---")
        print(soup.prettify()[:2000])
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pbc()
