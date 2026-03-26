
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from api.exchange_rate import get_all_rates, get_hangseng_rates

def test_integration():
    print("Testing get_all_rates integration...")
    try:
        data = get_all_rates()
        print("Keys:", data.keys())
        
        hs_rates = data.get("hangseng", [])
        print(f"Hang Seng Rates Count: {len(hs_rates)}")
        
        if len(hs_rates) > 0:
            print("Sample Hang Seng Rate:", hs_rates[0])
            is_mock = any("模拟" in str(r.get("pub_time", "")) for r in hs_rates)
            print(f"Is Mock Data: {is_mock}")
        else:
            print("No Hang Seng rates returned.")
            
    except Exception as e:
        print(f"Integration Error: {e}")

if __name__ == "__main__":
    test_integration()
