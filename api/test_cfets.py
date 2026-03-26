import requests
from datetime import datetime

def test_cfets():
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
    }
    # ZwBkCcpr 获取当日行情，通常带有标签
    url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/ZwBkCcpr"
    
    print(f"Testing URL: {url}")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()
        print("Keys:", data.keys())
        if 'records' in data and len(data['records']) > 0:
            print("First Record:", data['records'][0])
        if 'head' in data:
            print("Head:", data['head'])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_cfets()
