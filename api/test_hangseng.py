import requests
from bs4 import BeautifulSoup

def test_hangseng():
    url = "https://www.hangseng.com/zh-cn/personal/banking/rates/foreign-exchange-rates/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'utf-8'
        print(f"Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Look for table data
        # Common currencies to check
        keywords = ["美元", "USD", "人民币", "CNY"]
        found = False
        for kw in keywords:
            if kw in resp.text:
                print(f"Found keyword by text search: {kw}")
                found = True
        
        if not found:
            print("Keywords not found in raw text. Might be dynamic.")
            
        # Try to find table
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables.")
        
        for i, table in enumerate(tables):
            print(f"--- Table {i} ---")
            rows = table.find_all('tr')
            for j, row in enumerate(rows):
                cols = row.find_all(['td', 'th'])
                texts = [c.text.strip() for c in cols]
                print(f"  Row {j}: len={len(cols)}, content={texts}")

        if "USD" in resp.text:
            idx = resp.text.find("USD")
            print(f"Found 'USD' at index {idx}")
            print(f"Context: {resp.text[idx-100:idx+200]}")
        else:
            print("'USD' not found in response text.")

        # Try to find a JSON like structure
        import re
        json_matches = re.findall(r'\{[^{}]*"currency"[^{}]*\}', resp.text)
        if json_matches:
            print(f"Found {len(json_matches)} potential JSON objects")
            print(json_matches[0])

    except Exception as e:
        print(f"Error: {e}")

def test_json_api():
    candidates = [
        "https://www.hangseng.com/cms/invest/fx/fx-rates-full-list.json",
        "https://www.hangseng.com/content/dam/hase/config/personal/banking/rates/foreign-exchange-rates/rates_zh_CN.json",
        "https://www.hangseng.com/live/json/hangseng/retail/invest/fx-rates-full-list.json"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.hangseng.com/zh-cn/personal/banking/rates/foreign-exchange-rates/",
        "Origin": "https://www.hangseng.com",
        "Accept": "application/json, text/plain, */*"
    }

    print("\n--- Testing JSON APIs ---")
    for url in candidates:
        print(f"Testing {url} ...")
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print("Success! Head of content:")
                print(resp.text[:500])
                # Try parsing JSON
                try:
                    data = resp.json()
                    print("Valid JSON structure found.")
                    # Check for USD
                    print("Keys:", data.keys() if isinstance(data, dict) else "List found")
                except:
                    print("Not valid JSON.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_json_api()
    # test_hangseng()
